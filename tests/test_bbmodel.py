"""Tests básicos del algoritmo A (sin red ni datos reales)."""
import numpy as np
import pandas as pd

from bbmodel import enlace, identidad
from bbmodel.metricas import CATALOGO, destransformar, transformar


def test_clave_nombre_ordena_y_limpia():
    assert identidad.clave_nombre("LLULL, SERGIO") == identidad.clave_nombre("Sergio Llull")
    assert identidad.clave_nombre("Kevin Porter Jr.") == "kevin porter"
    assert identidad.clave_nombre("Nikola Jokić") == "jokic nikola"


def test_transformaciones_son_inversas():
    for m in CATALOGO.values():
        x = np.array([0.5, 5.0, 25.0, 60.0]) if m.transf != "id" else np.array([-3.0, 0.0, 15.0, 110.0])
        assert np.allclose(destransformar(transformar(x, m.transf), m.transf), x)


def _fila(liga, temp, pid, nombre, edad, gp, team_gp=34):
    return {"liga": liga, "temporada": temp, "anio": int(temp[:4]), "player_id": pid, "nombre": nombre,
            "edad": edad, "fecha_nacimiento": np.nan, "gp": gp, "team_gp": team_gp}


def test_homonimos_se_separan_por_edad_y_calendario():
    t = pd.DataFrame([
        _fila("euroleague", "2025-26", "1", "BOOKER, DEVIN", 34, 30),
        _fila("nba", "2025-26", "b", "Devin Booker", 29, 70, 82),
        _fila("lba", "2025-26", "9", "Devin Booker", np.nan, 12),   # sin edad: sólo cabe el de Milán
        _fila("acb", "2025-26", "7", "Sergio Llull", np.nan, 30),
        _fila("euroleague", "2025-26", "2", "LLULL, SERGIO", 38, 30),
    ])
    r, _ = identidad.resolver(t)
    pid = dict(zip(r["liga"] + r["nombre"], r["persona_id"]))
    assert pid["euroleagueBOOKER, DEVIN"] != pid["nbaDevin Booker"]
    assert pid["lbaDevin Booker"] == pid["euroleagueBOOKER, DEVIN"]
    assert pid["acbSergio Llull"] == pid["euroleagueLLULL, SERGIO"]


def test_enlace_recupera_un_tipo_de_cambio_conocido():
    """Datos simulados: la liga B vale m = −0,6 y s = 0,8 en la vara EuroLeague. Se prueban enlaces en
    la misma temporada, entre temporadas y mezclados."""
    for modo in ("misma", "siguiente", "mezcla"):
        rng = np.random.default_rng(0)
        filas = []
        for p in range(1500):
            a = rng.normal(-0.3, 1.0)
            z_el = a + rng.normal(0, 0.4)
            z_b = (a + 0.6) / 0.8 + rng.normal(0, 0.4)
            sig = modo == "siguiente" or (modo == "mezcla" and p % 2)
            filas += [{"persona_id": p, "liga": "euroleague", "anio": 2024, "anio_nac": 1997, "min": 600, "z": z_el, "v": 0.1},
                      {"persona_id": p, "liga": "acb", "anio": 2024 + sig, "anio_nac": 1997, "min": 600, "z": z_b, "v": 0.1}]
        r = enlace.ajustar_metrica(pd.DataFrame(filas), n_boot=0)
        assert abs(r["m"]["acb"] + 0.6) < 0.1, (modo, r["m"])
        assert abs(r["s"]["acb"] - 0.8) < 0.1, (modo, r["s"])


# ---------------------------------------------------------------- nacionalidad y dataset normalizado
def test_nacionalidad_unifica_nombres_de_pais():
    from bbmodel.nacionalidad import codigo, nombre_pais
    assert codigo("United States of America") == codigo("USA") == codigo("US") == "US"
    assert codigo("Congo, Democratic Republic of the") == codigo("DRC") == "CD"
    assert codigo("Türkiye") == codigo("Turkey") == "TR"
    assert codigo("España") == "ES" and codigo("") is None and codigo(None) is None
    assert nombre_pais("US|GH") == "Estados Unidos / Ghana" and nombre_pais(float("nan")) is None


def test_combinar_usa_a_cuando_falta_b():
    import numpy as np
    import pandas as pd
    from bbmodel.dataset_normalizado import combinar
    a = pd.Series([0.50, 0.40, np.nan])
    b = pd.Series([0.60, np.nan, 0.30])
    ab = combinar(a, b, "ts_pct")
    assert 0.50 < ab[0] < 0.60 and ab[1] == 0.40 and ab[2] == 0.30
