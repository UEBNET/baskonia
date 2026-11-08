"""F1 · Motor de escenarios del ecosistema del club (encargo v4.1 §3.1–3.2 y §4 F1). Composición de lo existente: no
aprende ningún modelo nuevo.

    R' = (R ∪ A) ∖ D           R = plantilla de partida, A = altas (cada una con rol fijado por el analista), D = bajas

Para cada escenario:
  · Minutos: motor de minutos v3.3 (Plackett-Luce con los pesos de producto, `Equipo.plantilla_minutos`) sobre R'; a las
    ALTAS con rol fijado se les impone su franja de minutos con `bbfit.simulador.forzar_roles` (la v3.3; el resto de la
    plantilla reparte lo que queda). Los jugadores que ya estaban conservan su rol de partida: el motor decide sus minutos.
    Recorte a [0, duración del partido] y Σ = 5 × duración exacta en cada simulación (decisión P5).
  · Uso: USG% «natural» de cada jugador traducido a la liga de destino (`bbfit.simulador._uso_natural`, la v3.3) y regla de
    suma fija (`redistribuir_uso`) con amortiguación 1: en cada simulación Σ minutos·USG = 20·Σ minutos (los cinco en
    pista suman el 100 %).
  · Equipo: T(R') = Σ p_i β_i + Σ_{i<j} P_ij φ_ij + Σ p_i h_i por simulación (`equipo.valor_equipo`, la capa 4), y
    Δ̂Net = c·(T(R') − T̄(R)) + (d − 1)·Net_actual, con la calibración (c, d, s0, q) del grupo de liga, exactamente como
    `Equipo.delta` (misma semilla ⇒ mismo resultado: prueba de paridad).
  · Impacto cruzado por compañero (métricas validadas de F2-B: cuota de tiro, % de canastas asistidas, pts/100): para el
    movimiento k (alta X o baja A) y el compañero Y, Δ_Y = ± π_YX · d̂(X → Y), con π_YX = fracción de las posesiones de Y
    con X en pista (P_XY / p_Y, la misma aproximación de parejas de la capa 4). Rango del 80 % con la calibración de F2-B
    escalada por π; varios movimientos se suman (rangos en cuadratura, independencia supuesta) [HIPÓTESIS declarada].
  · Atribución: valores de Shapley del cambio de valor del equipo y de los minutos y el uso de cada jugador sobre el
    conjunto de movimientos M = A ∪ D; exactos si |M| ≤ 4 (2^|M| escenarios con números aleatorios comunes), por
    permutaciones si |M| > 4 (error Monte Carlo declarado). Química entre dos altas a y b: Δ({a,b}) − Δ({a}) − Δ({b}).
  · Valor de baja (nombre provisional): lo que cae el valor del equipo sin el jugador, con sus minutos redistribuidos por
    el motor, c·(T̄(R) − T̄(R ∖ {j})). Sin examen todavía (banco V-AUS, F3).

Identidad contable (comprobada en cada llamada): Δ̂Net = Σ_k φ_k + diferencia Monte Carlo de la base + regresión a la media.
"""
from __future__ import annotations

import json
import math
from itertools import combinations, permutations

import numpy as np
import pandas as pd

from . import config as CE

EFECTOS = ("d_cuota_tiro", "d_pct_asistidas", "d_pts100")


# =============================================================================================== minutos y uso
def ajustar_suma(M: np.ndarray, total: float, tope: float, fijos: np.ndarray | None = None, it: int = 100) -> np.ndarray:
    """Recorta cada jugador a [0, tope] y reparte el desajuste para que cada simulación sume `total` exactamente, en
    proporción a los minutos de los jugadores que aún tienen margen; los de rol fijado sólo se tocan si no queda otro
    remedio. Si la simulación ya cumple, no cambia nada (necesario para la paridad con la capa 4)."""
    M = np.clip(np.asarray(M, float).copy(), 0.0, tope)
    n = M.shape[1]
    fij = np.zeros(n, bool) if fijos is None else np.asarray(fijos, bool)
    for _ in range(it):
        dif = total - M.sum(1)
        malas = np.nonzero(np.abs(dif) >= 1e-9)[0]
        if not len(malas):
            break
        for s in malas:
            margen = (M[s] < tope - 1e-12) if dif[s] > 0 else (M[s] > 1e-12)
            for grupo in (margen & ~fij, margen):                    # primero los libres; si no hay, también los fijados
                if grupo.any():
                    base = np.where(grupo, M[s], 0.0)
                    if base.sum() <= 0:
                        base = grupo.astype(float)
                    M[s] = np.clip(M[s] + dif[s] * base / base.sum(), 0.0, tope)
                    break
    return M


def pares_en_pista(Pm: np.ndarray) -> np.ndarray:
    """E[P_ij] (n × n): fracción de las posesiones del equipo con i y j en pista, P_ij ≈ p_i p_j · 10 / Σ_{i<j} p_i p_j
    por simulación (la aproximación de parejas de la capa 4), promediada sobre las simulaciones."""
    pp = (Pm.sum(1) ** 2 - (Pm ** 2).sum(1)) / 2.0
    P = np.einsum("si,sj->ij", Pm, Pm * (10.0 / np.maximum(pp, 1e-9))[:, None]) / Pm.shape[0]
    np.fill_diagonal(P, 0.0)
    return P


# =============================================================================================== el ecosistema
class Ecosistema:
    """Motor de escenarios sobre la capa 4 de producción (`bbequipo.equipo.Equipo`) de una temporada."""

    def __init__(self, cfg: dict, temporada: str, equipo=None, progreso=print):
        import pickle
        from .. import equipo as EQ
        self.cfg = cfg
        self.cfg40 = CE.cargar_v40(cfg)
        self.eq = equipo or EQ.Equipo(self.cfg40, temporada, progreso=progreso)
        self.EQ = EQ
        self.temp = temporada
        p = CE.RAIZ / self.cfg40["f2"]["salida"] / "dirigidos" / "modelos.pkl"
        self.f2b = pickle.loads(p.read_bytes())
        self.f1c = cfg["f1"]
        # β de ataque y defensa (F1 v4.0 publicado, el más reciente ≤ temporada) para el reparto ORtg / DRtg del Δ
        od = []
        for f in sorted((CE.RAIZ / self.cfg40["f1"]["salidas"]["rapm"]).glob("20??-??.csv.gz")):
            if f.name[:7] <= temporada:
                od.append(pd.read_csv(f, usecols=["persona_id", "temporada", "beta_of", "beta_def"]))
        od = pd.concat(od).sort_values("temporada").drop_duplicates("persona_id", keep="last") if od else pd.DataFrame()
        self.b_of = dict(zip(od.get("persona_id", []), od.get("beta_of", [])))
        self.b_def = dict(zip(od.get("persona_id", []), od.get("beta_def", [])))
        # F2: referencia del Impacto en pista (impacto_pista/referencia_impacto_pista.json) y referencias NC de la v4.0
        pr = CE.RAIZ / cfg["salida"] / "impacto_pista" / "referencia_impacto_pista.json"
        self.ref_ip = json.loads(pr.read_text(encoding="utf-8")) if pr.exists() else None
        da = CE.RAIZ / self.cfg40["salida"] / "equipo" / "anclas"
        t1 = f"{int(temporada[:4]) + 1}-{str(int(temporada[:4]) + 2)[-2:]}"
        cand = [da / f"referencias_nc_{t1}.json", da / f"referencias_nc_{temporada}.json"] + sorted(da.glob("referencias_nc_*.json"), reverse=True)
        self.ref_nc = next((json.loads(f.read_text(encoding="utf-8")) for f in cand if f.exists()), None)
        pc = CE.RAIZ / cfg["salida"] / "escenarios" / "minutos_calibracion.json"
        self.cal_min = json.loads(pc.read_text(encoding="utf-8"))["producto"] if pc.exists() else None
        # El motor de producción de la capa 4 corre con la configuración de corte de la v3.2, que no trae el bloque
        # `rol_asignado` (lo añadió la v3.3, con los mismos valores que simulation.yaml). Se toma en SÓLO LECTURA de
        # configs/simulation_v33.yaml para que forzar_roles (v3.3) pueda imponer el rol de las altas.
        if "rol_asignado" not in self.eq.c.cfg:
            import yaml
            v33 = yaml.safe_load((CE.RAIZ / "configs" / "simulation_v33.yaml").read_text(encoding="utf-8"))
            self.eq.c.cfg["rol_asignado"] = v33["rol_asignado"]

    # ---------------------------------------------------------------- un escenario (una plantilla)
    def escenario(self, liga: str, team_id: str, miembros: list[tuple[str, float]], roles: dict[str, str], n_sim: int,
                  semilla: int, aplicar_p5: bool = True) -> dict:
        eq, S = self.eq, self.eq.S
        gm = float(S.minutos_partido(liga))
        P, Pm = eq.plantilla_minutos(liga, team_id, miembros, n_sim, semilla)
        pids = list(P["persona_id"].astype(str))
        M = Pm * gm
        fuerza = {pids.index(p): r for p, r in roles.items() if p in pids and r}
        if fuerza:
            S.forzar_roles(M, fuerza, 5 * gm, gm, liga, eq.c, np.random.default_rng(semilla + 7777))
        fij = np.array([i in fuerza for i in range(len(pids))])
        if aplicar_p5:                                                # P5: recorte y Σ minutos exacta
            M = ajustar_suma(M, 5 * gm, gm, fij)
        Pm2 = M / gm
        rng = np.random.default_rng(semilla)                          # mismo flujo que Equipo.fuerza (paridad)
        v = self.EQ.valor_equipo(eq, liga, pids, Pm2, rng)
        # uso: natural traducido a la liga (v3.3) y suma fija exacta (amortiguación de la capa E)
        ref = eq.c.ref["uso"].get(liga, (20.0, 5.0))
        usg = np.full(len(P), np.nan)
        for i, r in P.reset_index(drop=True).iterrows():
            rr = r.get("_reg")
            if isinstance(rr, dict):
                usg[i] = S._uso_natural(eq.c, rr, liga)[0]
        usg = np.clip(np.where(np.isfinite(usg), usg, ref[0] - 0.5 * ref[1]), 5, 45)
        U2, _ = S.redistribuir_uso(M, np.repeat(usg[None, :], n_sim, 0), float(self.f1c["uso_medio_pista"]),
                                   float(self.f1c["uso_amortiguar"]))
        return {"pids": pids, "P": P, "M": M, "Pm": Pm2, "v": v, "usg_natural": usg, "USG": U2, "gm": gm,
                "fijos": {pids[i]: r for i, r in fuerza.items()}}

    def _cal(self, liga: str) -> tuple[float, float, float, float]:
        cal = self.eq.cal["por_grupo"].get(self.EQ.GRUPOS_LIGA.get(liga, "otras"), self.eq.cal["conjunto"])
        return cal["prediccion"]["c"], cal["prediccion"]["d"], cal["intervalo"]["s0"], cal["intervalo"]["q"]

    # ---------------------------------------------------------------- impacto cruzado (F2-B)
    def cruzado(self, mov: str, X: str, esc: dict) -> pd.DataFrame:
        """Δ de cada compañero Y por el movimiento de X (alta: en el escenario con X; baja: en el escenario con A)."""
        from .. import dirigidos as DG
        pids = esc["pids"]
        if X not in pids:
            return pd.DataFrame()
        ix = pids.index(X)
        R = self.f2b["rasgos"]
        clave = lambda p: f"{p}|{self.temp}"  # noqa: E731
        Z = R.de([clave(p) for p in pids])
        P = pares_en_pista(esc["Pm"])
        p = esc["Pm"].mean(0)
        otros = [i for i in range(len(pids)) if i != ix]
        if not otros:
            return pd.DataFrame()
        pred = DG.predecir(self.f2b, np.repeat(Z[ix][None, :], len(otros), 0), Z[otros])
        signo = 1.0 if mov == "alta" else -1.0
        pi = np.array([P[i, ix] / max(p[i], 1e-9) for i in otros])     # fracción de las posesiones de Y con X en pista
        out = pd.DataFrame({"persona_id": [pids[i] for i in otros], "movimiento": f"{mov}:{X}", "pi_con": pi})
        con_perfil = (np.abs(Z[ix]).sum() > 0) & (np.abs(Z[otros]).sum(1) > 0)
        for k in EFECTOS:
            if k not in pred:
                continue
            d, lo, hi = pred[k]
            out[k] = np.where(con_perfil, signo * pi * d, np.nan)
            a, b = signo * pi * lo, signo * pi * hi
            out[f"{k}_lo80"] = np.where(con_perfil, np.minimum(a, b), np.nan)
            out[f"{k}_hi80"] = np.where(con_perfil, np.maximum(a, b), np.nan)
        return out

    # ---------------------------------------------------------------- simular
    # ---------------------------------------------------------------- F2 · Impacto en pista y NC por escenario
    def impacto_en_pista(self, liga: str, e: dict, semilla: int = 0) -> pd.DataFrame:
        """Impacto en pista de cada jugador del escenario (v_j con los compañeros y minutos del escenario → percentil del
        grupo de liga → calibración isotónica al on/off; rango del 80 % por deciles). Sello según la puerta F2-a."""
        from . import impacto_pista as IP
        if self.ref_ip is None:
            return pd.DataFrame()
        if not hasattr(self, "_ins_ip"):
            self._ins_ip = IP.InsumosProduccion(self.eq)
        r = IP.valor_en_pista(self._ins_ip, liga, e["pids"], e["Pm"], np.random.default_rng(semilla + 99))
        out = IP.escala_producto(self.ref_ip, liga, self.cfg40, r["v"])
        out.insert(0, "persona_id", e["pids"])
        out["ip_sinergia"] = r["syn"]
        return out.set_index("persona_id")

    def nc_escenario(self, liga: str, team_id: str, e: dict, roles: dict[str, str], n_sim: int = 400) -> pd.DataFrame:
        """F2-b: NC₁ (con adaptación) y NC₂ (sin ella) de cada jugador CON los compañeros del escenario: el simulador v3.3
        de la v4.0 (S.simular) con miembros = el resto de la plantilla del escenario y los roles fijados de las altas."""
        from ..anclas import nivel_cerno
        S, c = self.eq.S, self.eq.c
        if self.ref_nc is None:
            return pd.DataFrame()
        pres = {p: float(x) for p, x in zip(e["P"]["persona_id"].astype(str), e["P"]["presencia"])} if "presencia" in e["P"] else {}
        filas = []
        for p in e["pids"]:
            mi = [(q, pres.get(q, 1.0)) for q in e["pids"] if q != p]
            otros = {q: r for q, r in roles.items() if q != p and r}
            fi = S.jugador_insumos(c, p)
            p3 = fi.get("pos3") if fi and isinstance(fi.get("pos3"), str) else None
            fila = {"persona_id": p}
            for k, sa in (("NC1", False), ("NC2", True)):
                res = S.simular(c, p, liga, team_id, mi, n_sim=n_sim, detalle=False, sin_adaptacion=sa,
                                rol=roles.get(p), roles=otros or None)
                if "error" in res:
                    continue
                nc = nivel_cerno(res, liga, p3, self.ref_nc)
                fila.update({k: nc.get("NC"), f"{k}_lo80": nc.get("NC_lo80"), f"{k}_hi80": nc.get("NC_hi80")})
            filas.append(fila)
        return pd.DataFrame(filas).set_index("persona_id")

    def simular(self, liga: str, team_id: str, plantilla: list[tuple[str, float]], altas: list[tuple[str, str | None]],
                bajas: list[str], net_actual: float, n_sim: int | None = None, semilla: int = 0,
                paridad_capa4: bool = False, aplicar_p5: bool = True, impacto_pista: bool = True, nc: bool = False) -> dict:
        """API del encargo: ecosistema.simular(R, altas=[(id, rol)], bajas=[id]) → equipo, jugadores, atribución, rangos.
        `paridad_capa4`: la base usa la semilla s y los escenarios s + 1, como `Equipo.delta` (prueba de paridad); por
        defecto todos comparten la semilla (números aleatorios comunes) y la diferencia Monte Carlo de la base es 0.
        `aplicar_p5=False` sólo para diagnóstico: no corrige las simulaciones del motor que no reparten todos los minutos."""
        n_sim = int(n_sim or self.f1c["monte_carlo"]["simulaciones"])
        team_id = str(team_id)
        R0 = [(str(p), float(x)) for p, x in plantilla]
        en_R0 = {p for p, _ in R0}
        bajas = [str(b) for b in bajas if str(b) in en_R0]
        altas = [(str(a), r) for a, r in altas if str(a) not in en_R0]
        movs = [("alta", a, r) for a, r in altas] + [("baja", b, None) for b in bajas]
        m = len(movs)
        c, d, s0, q = self._cal(liga)
        cache: dict[frozenset, dict] = {}
        base = self.escenario(liga, team_id, R0, {}, n_sim, semilla, aplicar_p5) if paridad_capa4 else None

        def esc_de(Sm: frozenset) -> dict:
            if Sm not in cache:
                fuera = {movs[i][1] for i in Sm if movs[i][0] == "baja"}
                R = [(p, x) for p, x in R0 if p not in fuera] + [(movs[i][1], 1.0) for i in sorted(Sm) if movs[i][0] == "alta"]
                roles = {movs[i][1]: movs[i][2] for i in Sm if movs[i][0] == "alta" and movs[i][2]}
                cache[Sm] = self.escenario(liga, team_id, R, roles, n_sim, semilla + 1, aplicar_p5)   # números aleatorios comunes
            return cache[Sm]

        todos = sorted({p for p, _ in R0} | {a for a, _ in altas})
        idx = {p: i for i, p in enumerate(todos)}

        def vector(e: dict) -> np.ndarray:
            """[c·T̄, minutos medios de cada jugador (0 si no está), uso medio ponderado por minutos (NaN si no está)]."""
            mins = np.zeros(len(todos)); usos = np.full(len(todos), np.nan)
            mm = e["M"].mean(0)
            uu = (e["USG"] * e["M"]).sum(0) / np.maximum(e["M"].sum(0), 1e-9)
            for j, p in enumerate(e["pids"]):
                mins[idx[p]], usos[idx[p]] = mm[j], uu[j]
            return np.r_[c * e["v"]["T"].mean(), mins, usos]

        vac = frozenset()
        v0 = vector(esc_de(vac))
        if base is None:
            base = esc_de(vac)                                                  # misma semilla que los escenarios
        exacto = m <= int(self.f1c["shapley"]["exacto_hasta"])
        phi = np.zeros((m, len(v0)))
        err = np.zeros((m, len(v0)))
        if m and exacto:
            for k in range(m):
                resto = [i for i in range(m) if i != k]
                for r in range(len(resto) + 1):
                    w = math.factorial(r) * math.factorial(m - r - 1) / math.factorial(m)
                    for Sm in combinations(resto, r):
                        a = vector(esc_de(frozenset(Sm) | {k})); b = vector(esc_de(frozenset(Sm)))
                        phi[k] += w * (np.nan_to_num(a) - np.nan_to_num(b))
        elif m:
            rng = np.random.default_rng(semilla + 4242)
            nper = int(self.f1c["shapley"]["permutaciones"])
            acc = [[] for _ in range(m)]
            for _ in range(nper):
                orden = rng.permutation(m)
                Sm = frozenset()
                vb = np.nan_to_num(vector(esc_de(Sm)))
                for k in orden:
                    S2 = Sm | {int(k)}
                    va = np.nan_to_num(vector(esc_de(S2)))
                    acc[k].append(va - vb)
                    Sm, vb = S2, va
            for k in range(m):
                A = np.array(acc[k]); phi[k] = A.mean(0); err[k] = A.std(0) / np.sqrt(len(A))
        final = esc_de(frozenset(range(m)))
        dT = final["v"]["T"] - base["v"]["T"].mean()
        delta = c * dT + (d - 1.0) * net_actual
        sd = float(c * dT.std()); semi = q * math.sqrt(sd ** 2 + s0 ** 2)
        dm = float(delta.mean())
        dif_base = float(c * (esc_de(vac)["v"]["T"].mean() - base["v"]["T"].mean()))
        reg = float((d - 1.0) * net_actual)
        suma_phi = float(phi[:, 0].sum()) if m else 0.0
        # descomposición del Δ (capa 4) y reparto del aditivo: valor directo de quien entra/sale y minutos desplazados
        f0v, f1v = base["v"], final["v"]
        p0 = dict(zip(base["pids"], base["Pm"].mean(0))); p1 = dict(zip(final["pids"], final["Pm"].mean(0)))
        b0 = dict(zip(base["pids"], f0v["beta"])); b1 = dict(zip(final["pids"], f1v["beta"]))
        sigue = set(p0) & set(p1)
        directo = sum(p1[x] * b1[x] for x in set(p1) - sigue) - sum(p0[x] * b0[x] for x in set(p0) - sigue)
        desplaz = sum((p1[x] - p0[x]) * b1[x] for x in sigue)
        # reparto ataque / defensa del aditivo con β^O y β^D (sin calibración propia: experimental, sello BAJA)
        def od_(e):
            bo = np.array([self.b_of.get(x, np.nan) for x in e["pids"]]); bd = np.array([self.b_def.get(x, np.nan) for x in e["pids"]])
            bn = np.asarray(e["v"]["beta"], float)
            bo = np.where(np.isfinite(bo), bo, bn / 2); bd = np.where(np.isfinite(bd), bd, -bn / 2)
            pm = e["Pm"].mean(0)
            return float(pm @ bo), float(pm @ bd)
        (o0, d0), (o1, d1) = od_(base), od_(final)
        desc_od = {"d_ortg": float(c * (o1 - o0)), "d_drtg": float(c * (d1 - d0)),
                   "nota": "reparto del aditivo con β de ataque y defensa (F1 v4.0); sin calibración propia: experimental, sello BAJA"}
        desc = {"aditivo_beta": float(c * (f1v["T_aditivo"] - f0v["T_aditivo"].mean()).mean()),
                "de_ello_valor_directo_altas_bajas": float(c * directo),
                "de_ello_minutos_desplazados": float(c * desplaz),
                "sinergia_phi": float(c * (f1v["T_phi"] - f0v["T_phi"].mean()).mean()),
                "correccion_jugador_h": float(c * (f1v["T_h"] - f0v["T_h"].mean()).mean()),
                "regresion_a_la_media": reg}
        # jugadores
        def resumen(e):
            M, U = e["M"], e["USG"]
            return pd.DataFrame({"persona_id": e["pids"], "min_media": M.mean(0), "min_p10": np.quantile(M, 0.1, 0),
                                 "min_p90": np.quantile(M, 0.9, 0),
                                 "usg": (U * M).sum(0) / np.maximum(M.sum(0), 1e-9), "beta": e["v"]["beta"],
                                 "fuente_beta": e["v"]["fuente"]}).set_index("persona_id")
        A0, A1 = resumen(base), resumen(final)
        if self.cal_min:                                   # P5: rangos de minutos recalibrados de la capa E (minutos_cal.py)
            from .minutos_cal import aplicar
            for A, e in ((A0, base), (A1, final)):
                r = aplicar(self.cal_min, A["min_media"].to_numpy(), e["gm"])
                for k in ("lo80", "hi80", "lo90", "hi90"):
                    A[f"min_{k}"] = r[k]
        J = A0.add_suffix("_antes").join(A1.add_suffix("_despues"), how="outer")
        J["estado"] = ["alta" if p in {a for a, _ in altas} else "baja" if p in set(bajas) else "sigue" for p in J.index]
        J["rol_fijado"] = [dict(altas).get(p) for p in J.index]
        J["d_min"] = J["min_media_despues"].fillna(0) - J["min_media_antes"].fillna(0)
        J["d_usg"] = J["usg_despues"] - J["usg_antes"]
        # F2: Impacto en pista (antes / después) y, si se pide, NC₁/NC₂ con los compañeros de cada plantilla
        if impacto_pista and self.ref_ip is not None:
            for e, suf in ((base, "_antes"), (final, "_despues")):
                J = J.join(self.impacto_en_pista(liga, e, semilla).add_suffix(suf), how="left")
            J["d_impacto_pista"] = J["impacto_pista_despues"] - J["impacto_pista_antes"]
        if nc:
            roles_alta = {a: r for a, r in altas if r}
            J = J.join(self.nc_escenario(liga, team_id, base, {}).add_suffix("_antes"), how="left")
            J = J.join(self.nc_escenario(liga, team_id, final, roles_alta).add_suffix("_despues"), how="left")
        # impacto cruzado F2-B por movimiento
        cr = [self.cruzado("alta", a, final) for a, _ in altas] + [self.cruzado("baja", b, base) for b in bajas]
        CR = pd.concat([x for x in cr if len(x)], ignore_index=True) if any(len(x) for x in cr) else pd.DataFrame()
        if len(CR):
            CRs = CR[CR["persona_id"].isin([p for p in J.index if J.loc[p, "estado"] == "sigue"])]
            for k in EFECTOS:
                if k in CRs:
                    g = CRs.groupby("persona_id")
                    J[k] = g[k].sum(min_count=1)
                    semi_k = g.apply(lambda x: np.sqrt(np.nansum(((x[f"{k}_hi80"] - x[f"{k}_lo80"]) / 2) ** 2)))
                    J[f"{k}_lo80"] = J[k] - semi_k
                    J[f"{k}_hi80"] = J[k] + semi_k
        # atribución (Shapley) por movimiento: equipo y, por jugador, minutos y uso
        n = len(todos)
        atrib_eq = pd.DataFrame({"movimiento": [f"{t}:{p}" for t, p, _ in movs], "phi_valor_equipo": phi[:, 0] if m else [],
                                 "error_mc": err[:, 0] if m else []})
        filas = []
        for k in range(m):
            for j, p in enumerate(todos):
                filas.append({"movimiento": f"{movs[k][0]}:{movs[k][1]}", "persona_id": p, "phi_min": phi[k, 1 + j],
                              "phi_usg": phi[k, 1 + n + j] if J.loc[p, "estado"] == "sigue" else np.nan})
        atrib_j = pd.DataFrame(filas)
        quim = {}
        ia = [i for i, x in enumerate(movs) if x[0] == "alta"]
        for a, b in combinations(ia, 2):
            vab = vector(esc_de(frozenset({a, b})))[0]; va = vector(esc_de(frozenset({a})))[0]; vb = vector(esc_de(frozenset({b})))[0]
            quim[f"{movs[a][1]}+{movs[b][1]}"] = float(vab - va - vb + v0[0])
        # valor de baja: lo que cae el equipo sin el jugador (minutos redistribuidos), con números aleatorios comunes
        vb_ = {}
        for i, (t, p, _) in enumerate(movs):
            if t == "baja":
                dif = c * (esc_de(vac)["v"]["T"] - esc_de(frozenset({i}))["v"]["T"])
                vb_[p] = {"valor_de_baja": float(dif.mean()), "lo80": float(np.quantile(dif, 0.1)), "hi80": float(np.quantile(dif, 0.9)),
                          "nota": "incertidumbre del modelo (β y minutos); sin examen (banco V-AUS, F3)"}
        control = {"escenarios_simulados": len(cache) + int(paridad_capa4), "shapley_exacto": exacto,
                   "identidad_contable": float(dm - (suma_phi + dif_base + reg)),
                   "suma_minutos_max_desvio": float(max(abs(e["M"].sum(1) - 5 * e["gm"]).max() for e in list(cache.values()) + [base])),
                   "minutos_fuera_de_limites": int(sum(((e["M"] < -1e-9) | (e["M"] > e["gm"] + 1e-9)).sum() for e in list(cache.values()) + [base])),
                   "cuota_tiro_renormalizada": False,
                   "uso_desvio_max": float(max(np.abs((e["USG"] * e["M"]).sum(1) - float(self.f1c["uso_medio_pista"]) * e["M"].sum(1)).max() /
                                               (5 * e["gm"]) for e in list(cache.values()) + [base]))}
        return {"equipo": {"net_actual": float(net_actual), "delta_net": dm, "lo80": dm - semi, "hi80": dm + semi,
                           "net_proyectado": float(net_actual + dm), "net_lo80": float(net_actual + dm - semi),
                           "net_hi80": float(net_actual + dm + semi), "sd_mc": sd, "s0": s0, "q": q, "c": c, "d": d,
                           "descomposicion": desc, "ataque_defensa": desc_od, "suma_shapley": suma_phi,
                           "diferencia_mc_base": dif_base},
                "jugadores": J.reset_index().rename(columns={"index": "persona_id"}), "cruzado_detalle": CR,
                "atribucion_equipo": atrib_eq, "atribucion_jugadores": atrib_j, "quimica_altas": quim,
                "valor_de_baja": vb_, "control": control,
                "meta": {"version": self.cfg["version"], "temporada": self.temp, "liga": liga, "team_id": team_id,
                         "n_sim": n_sim, "semilla": semilla, "paridad_capa4": paridad_capa4, "movimientos": [f"{t}:{p}" + (f"({r})" if r else "") for t, p, r in movs]}}
