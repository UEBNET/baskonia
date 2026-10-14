"""Tests de bbestilo (sin datos reales: plantillas sintéticas y redes diminutas)."""
import math

import numpy as np
import pandas as pd
import pytest

torch = pytest.importorskip("torch", reason="bbestilo necesita torch (requirements-estilos.txt)")

from bbestilo import config as C  # noqa: E402
from bbestilo import datos, entrenar  # noqa: E402
from bbestilo.redes import RedVaDE  # noqa: E402


def _plantilla(n=10, seed=0):
    rng = np.random.default_rng(seed)
    R = np.column_stack([
        np.full(n, 0.4),                       # ritmo_rel (igual para toda la plantilla)
        rng.uniform(10, 60, n),                # fg3a_rate
        rng.uniform(10, 50, n),                # fta_rate
        rng.uniform(5, 35, n),                 # ast_pct
        rng.uniform(8, 20, n),                 # tov_pct
        rng.uniform(0.5, 6, n),                # oreb_p100
        rng.uniform(2, 10, n),                 # dreb_p100
        rng.uniform(0.5, 3, n),                # stl_p100
        rng.uniform(0, 2.5, n),                # blk_p100
        rng.uniform(3, 9, n),                  # pf_p100
        rng.uniform(12, 30, n),                # usg_pct
        (np.arange(n) % 3 == 0).astype(float),  # es_int
        (np.arange(n) % 3 == 1).astype(float),  # es_ext
    ])
    w = rng.uniform(50, 900, n)
    return R, w


def test_club_es_la_media_ponderada_de_sus_jugadores():
    R, w = _plantilla()
    club = datos.agregar(R, w[None])[0]
    u = R[:, datos._I["usg_pct"]]
    jug = datos.vectores_jugador(R, club, float(np.average(u, weights=w)))
    # TODOS los rasgos (también la concentración del uso y las cuotas por posición) son medias ponderadas exactas
    assert np.allclose(np.average(jug, axis=0, weights=w), club)
    assert club[C.COLS.index("uso_conc")] >= 1.0


def test_agregar_ignora_huecos_y_uso_repartido_vale_uno():
    R, w = _plantilla()
    R[:, datos._I["usg_pct"]] = 20.0
    R[0, datos._I["fg3a_rate"]] = np.nan
    club = datos.agregar(R, w[None])[0]
    assert math.isclose(club[C.COLS.index("uso_conc")], 1.0)
    esperado = np.average(R[1:, datos._I["fg3a_rate"]], weights=w[1:])
    assert math.isclose(club[C.COLS.index("fg3a_rate")], esperado)


def _cj_sintetico():
    R, w = _plantilla(8)
    Q = np.random.default_rng(3).normal(size=(8, len(C.NIVEL)))
    clubes = pd.DataFrame({"clave": ["x:1:2025-26"], "temporada": ["2025-26"], "provisional": [False]})
    jug = pd.DataFrame({"clave": ["x:1:2025-26"] * 8, "min": w})
    cj = datos.Conjunto(clubes, jug, {"x:1:2025-26": (R, w, np.arange(8), Q)})
    cj.escala_club = datos.Escala(np.zeros(len(C.COLS)), np.ones(len(C.COLS)))
    cj.escala_jugador = cj.escala_club
    return cj


def test_simular_sin_minutos_o_sustituyendose_a_si_mismo_no_mueve_al_club():
    from bbestilo.encaje import simular
    cj = _cj_sintetico()
    R, w, _, Q = cj.plantillas["x:1:2025-26"]
    club = datos.agregar(R, w[None])[0]
    qm = datos._media_w(Q, w[None])[0]
    v0, q0, _ = simular(cj, "x:1:2025-26", 3, minutos=0.0)
    assert np.allclose(v0, club) and np.allclose(q0, qm)
    v1, q1, m = simular(cj, "x:1:2025-26", 3, sustituye=3)
    assert math.isclose(m, w[3]) and np.allclose(v1, club) and np.allclose(q1, qm)


def test_simular_plantilla_varios_fichajes_y_bajas():
    from bbestilo.encaje import simular, simular_plantilla
    cj = _cj_sintetico()
    R, w, _, Q = cj.plantillas["x:1:2025-26"]
    T = w.sum()
    # dos «fichajes» (filas 1 y 2 de la propia plantilla, usadas como jugadores externos) y una baja (fila 0)
    v, q, mins = simular_plantilla(cj, "x:1:2025-26", [(1, 300.0), (2, 200.0)], [0])
    assert mins == [300.0, 200.0]
    resto = w.copy()
    resto[0] = 0.0
    W = np.concatenate([resto * (T - 500) / resto.sum(), [300.0, 200.0]])
    filas = np.vstack([R, R[1], R[2]])
    filas[-2:, C.COLS.index("ritmo_rel")] = datos.agregar(R, w[None])[0][C.COLS.index("ritmo_rel")]
    assert np.allclose(v, datos.agregar(filas, W[None])[0])
    assert math.isclose(W.sum(), T)
    # un solo fichaje que hereda los minutos de una baja = simular(..., sustituye=)
    a = simular(cj, "x:1:2025-26", 4, sustituye=5)
    b = simular_plantilla(cj, "x:1:2025-26", [(4, float(w[5]))], [5])
    assert np.allclose(a[0], b[0]) and np.allclose(a[1], b[1])
    with pytest.raises(ValueError):
        simular_plantilla(cj, "x:1:2025-26", [(1, T)], [])


def test_neutralizar_quita_la_relacion_con_el_nivel():
    rng = np.random.default_rng(5)
    L = rng.normal(size=400)
    X = np.column_stack([2 * L + rng.normal(size=400), L ** 2 + rng.normal(size=400), rng.normal(size=400)])
    n = datos._ajustar_neutralizador(X, L, np.ones(400))
    Xn = n.aplicar(X, L)
    for k in range(3):
        assert abs(np.corrcoef(Xn[:, k], L)[0, 1]) < 1e-6 and abs(np.corrcoef(Xn[:, k], L ** 2)[0, 1]) < 1e-6
    assert np.allclose(Xn.std(0), 1, atol=1e-6)
    assert n.r2[0] > 0.7 and n.r2[2] < 0.05


def test_indice_de_nivel_ignora_huecos():
    niv = datos.Nivel(np.zeros(3), np.ones(3), np.array([1.0, 1.0, -1.0]))
    assert np.allclose(niv.indice(np.array([[1.0, np.nan, -1.0], [np.nan] * 3])), [1.0, 0.0])


def test_las_redes_terminan_en_n_estilos_neuronas_y_un_mapa_3d():
    x = torch.randn(5, len(C.COLS))
    for red in (RedVaDE(len(C.COLS), k=C.N_ESTILOS, covarianza="completa"),
                RedVaDE(len(C.COLS), k=C.N_ESTILOS, covarianza="diag")):
        p = red.salida(x)
        assert p.shape == (5, C.N_ESTILOS)
        assert torch.allclose(p.sum(1), torch.ones(5), atol=1e-5)
        assert red.mapa(x).shape == (5, C.D_MAPA)


def _muestras(n=120, seed=0):
    g = torch.Generator().manual_seed(seed)
    centros = torch.randn(4, len(C.COLS), generator=g) * 2
    X = centros[torch.arange(n) % 4] + 0.3 * torch.randn(n, len(C.COLS), generator=g)
    return entrenar.Muestras(X, X + 0.05 * torch.randn(n, len(C.COLS), generator=g), X[:40], np.arange(n))


def test_entrenamiento_rapido_y_orientacion_conserva_distancias():
    M = _muestras()
    for tipo in entrenar.ENTRENADORES:
        red = entrenar.ENTRENADORES[tipo](M, 1, hp={"epocas_pre": 3, "epocas": 3, "lote": 64})
        red.eval()
        with torch.no_grad():
            antes = torch.pdist(red.codificar(M.Xc))
            etiq_antes = red.salida(M.Xc).argmax(1)
        entrenar.orientar(red, M.Xc)
        with torch.no_grad():
            despues = torch.pdist(red.mapa(M.Xc))
            etiq = red.salida(M.Xc).argmax(1)
        ratio = despues / antes.clamp_min(1e-9)
        assert torch.allclose(ratio, ratio.median().expand_as(ratio), rtol=1e-3)   # sólo rota y escala
        # reordenar los estilos permuta las neuronas sin cambiar qué clubes van juntos
        assert entrenar.adjusted_rand_score(etiq_antes.numpy(), etiq.numpy()) == 1.0


def _gelu(x):
    return 0.5 * x * (1 + np.tanh(0.7978845608028654 * (x + 0.044715 * x ** 3)))


def _red_desde_json(P, x):
    """Réplica en numpy del cálculo del navegador (artifact/mapa-estilos.html: mlp + redAplicar)."""
    h = x
    for i, c in enumerate(P["capas"]):
        h = np.array(c["W"]) @ h + np.array(c["b"])
        if i < len(P["capas"]) - 1:
            h = _gelu(h)
    mu, prec = np.array(P["salida"]["mu"]), np.array(P["salida"]["prec"])
    d = h - mu
    maha = np.einsum("ki,kij,kj->k", d, prec, d)
    logit = np.array(P["salida"]["log_pi"]) - 0.5 * (maha + np.array(P["salida"]["logdet"]) + 3 * np.log(2 * np.pi))
    p = np.exp(logit - logit.max())
    M = P["mapa"]
    return p / p.sum(), (h - np.array(M["centro"])) @ np.array(M["rot"]) * M["escala"]


def test_los_pesos_exportados_reproducen_la_red():
    M = _muestras()
    for tipo in entrenar.ENTRENADORES:
        red = entrenar.ENTRENADORES[tipo](M, 2, hp={"epocas_pre": 2, "epocas": 2, "lote": 64})
        red.eval()
        entrenar.orientar(red, M.Xc)
        P = entrenar.exportar_pesos(red, tipo)
        x = M.Xc[:6]
        with torch.no_grad():
            p_t, z_t = red.salida(x).numpy(), red.mapa(x).numpy()
        for i in range(6):
            p, z = _red_desde_json(P, x[i].numpy().astype(float))
            assert np.allclose(p, p_t[i], atol=2e-4) and np.allclose(z, z_t[i], atol=2e-4)


def test_enlace_de_clubes_por_nombre_y_plantilla():
    filas = []
    for t, tid, nombre in [("2023-24", "1", "Umana Reyer Venezia"), ("2024-25", "9", "Reyer Venezia"),
                           ("2023-24", "2", "Germani Brescia"), ("2024-25", "8", "Germani Basket Brescia")]:
        for k in range(5):
            filas.append({"liga": "lba", "temporada": t, "team_id": tid, "equipo": nombre, "nombre": f"Jugador {tid}{k} Apellido"})
    f = pd.DataFrame(filas)
    club = datos.enlazar_clubes(f)
    par = dict(zip(f["temporada"] + f["equipo"], club))
    assert par["2023-24Umana Reyer Venezia"] == par["2024-25Reyer Venezia"]
    assert par["2023-24Germani Brescia"] == par["2024-25Germani Basket Brescia"]
    assert par["2023-24Umana Reyer Venezia"] != par["2023-24Germani Brescia"]


def test_parecido_es_100_menos_el_percentil_de_la_distancia():
    from bbestilo.similares import parecido
    q = np.linspace(0, 10, 101)          # distancias de referencia: percentil p ↔ distancia p/10
    assert np.allclose(parecido(np.array([0.0, 5.0, 10.0, 20.0]), q), [100, 50, 0, 0])


def test_mismo_club_agrupa_las_competiciones_de_un_club():
    from bbestilo.similares import mismo_club
    assert mismo_club("euroleague:BAS") == {"euroleague:BAS", "acb:3"}
    assert mismo_club("lba:c001") == {"lba:c001"}
