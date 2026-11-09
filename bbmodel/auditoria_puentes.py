"""§13 (criterios del 02-11-2026) · auditoría de identidades de los jugadores PUENTE en las ligas con pocos puentes.

Muestra aleatoria (semilla fija) de 100 personas que juegan en una de las ligas con pocos puentes (FEB3, FEB2, CBA,
NBL, BNXT, NCAA) y en al menos otra liga. Una fila por persona con todos sus registros (liga, temporada, equipo,
nombre, año de nacimiento, nacionalidad, minutos) y los enlaces del crosswalk (método y confianza), más comprobaciones
automáticas que ayudan a la revisión manual:
  * años de nacimiento distintos entre registros (con dato en los dos);
  * nacionalidades distintas (con dato);
  * nombres sin ninguna palabra en común (normalizados, sin tildes ni sufijos Jr./III);
  * temporadas con tres o más ligas nacionales (dos es un traspaso a mitad de temporada; NBA + G League, habitual);
  * confianza mínima del enlace < 0,85.
La revisión la hace el usuario (columna «correcto»: sí/no) y el criterio es la cota inferior de Clopper-Pearson al
95 % de la precisión ≥ 0,95 (con n = 100: como mucho 1 error). Si no se cumple, se sube a ≥ 0,85 el umbral de fusión
de los puentes (distinto del 0,75 general) y se repite.

    python -m bbmodel auditoria-puentes   →  data/modelos/v3_2/auditoria_puentes/muestra_puentes.csv (+ LEEME.md)
    python -m bbmodel auditoria-puentes --evaluar   (con la columna «correcto» rellenada)
"""
from __future__ import annotations

import unicodedata

import numpy as np
import pandas as pd

from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

LIGAS_POCOS_PUENTES = ["ligau", "feb3", "feb2", "cba", "nbl", "bnxt", "ncaa"]
SUFIJOS = {"jr", "sr", "ii", "iii", "iv"}
COPAS = {"euroleague", "eurocup", "bcl", "fec"}       # compatibles con una liga nacional en la misma temporada
SALIDA = RAIZ / "data" / "modelos" / "v3_2" / "auditoria_puentes"


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return " ".join(s.replace(".", " ").replace("-", " ").split())


def _apellido(n: str) -> str:
    """Apellido normalizado: «APELLIDO, NOMBRE» → APELLIDO; «Nombre Apellido» o «N. Apellido» → la última palabra."""
    n = str(n)
    if "," in n:
        n = n.split(",")[0]
        p = _norm(n).split()
        return p[-1] if p else ""
    p = _norm(n).split()
    return p[-1] if p else ""


def _nac(x: str) -> str:
    """Nacionalidad comparable: código ISO de 2 letras si se puede (bbmodel.nacionalidad), si no el texto."""
    try:
        from .nacionalidad import codigo
        return codigo(x) or _norm(x)
    except Exception:  # noqa: BLE001
        x = _norm(x)
        return {"united states of america": "us", "usa": "us", "united states": "us"}.get(x, x)


def muestra(tabla: pd.DataFrame, n: int = 100, semilla: int = 20261102) -> pd.DataFrame:
    cw = pd.read_csv(RAIZ / "data" / "processed" / "player_id_crosswalk.csv", dtype=str)
    cw["confianza"] = pd.to_numeric(cw["confianza"], errors="coerce")
    ligas = tabla.groupby("persona_id")["liga"].agg(set)
    candidatos = sorted(p for p, ls in ligas.items() if len(ls) >= 2 and ls & set(LIGAS_POCOS_PUENTES))
    rng = np.random.default_rng(semilla)
    elegidos = rng.choice(candidatos, min(n, len(candidatos)), replace=False)
    filas = []
    for p in elegidos:
        g = tabla[tabla["persona_id"] == p].sort_values(["temporada", "liga"])
        c = cw[cw["persona_id"] == str(p)]
        regs = "; ".join(f"{r.liga} {r.temporada} {r.equipo} · «{r.nombre}» · nac. {'' if pd.isna(r.anio_nac) else int(r.anio_nac)}"
                         f" · {'' if pd.isna(r.nacionalidad) else r.nacionalidad} · {int(r.min)} min"
                         for r in g.itertuples())
        anios = set(g["anio_nac"].dropna().astype(int))
        nacs = set(_nac(x) for x in g["nacionalidad"].dropna().astype(str))
        # nombres sin ninguna palabra en común (sin sufijos jr/ii/iii ni iniciales; los no latinos no cuentan)
        toks = [set(w for w in _norm(x.replace(",", " ")).split() if len(w) > 1 and w not in SUFIJOS)
                for x in g["nombre"].dropna().astype(str)]
        toks = [t for t in toks if t]
        apes = set() if not toks or set.intersection(*toks) else {" ".join(sorted(t)) for t in toks}
        sol = []
        for t, h in g.groupby("temporada"):
            ls = set(h["liga"]) - COPAS
            if ls >= {"nba", "gleague"}:
                ls -= {"gleague"}                   # NBA y G League en la misma temporada es habitual
            if len(ls) >= 3:                        # dos ligas = traspaso a mitad de temporada (habitual); tres, raro
                sol.append(f"{t}: {', '.join(sorted(ls))}")
        avisos = []
        if len(anios) > 1:
            avisos.append(f"años de nacimiento distintos {sorted(anios)}")
        if len(nacs) > 1:
            avisos.append(f"nacionalidades distintas {sorted(nacs)}")
        if len(apes) > 1:
            avisos.append(f"nombres sin palabras en común {sorted(apes)}")
        if sol:
            avisos.append("temporada con tres o más ligas nacionales: " + " | ".join(sol))
        cmin = float(c["confianza"].min()) if len(c) else np.nan
        if np.isfinite(cmin) and cmin < 0.85:
            avisos.append(f"confianza mínima del enlace {cmin:.2f}")
        filas.append({"persona_id": p, "ligas": ", ".join(sorted(set(g["liga"]))), "registros": len(g),
                      "nombres": " / ".join(sorted(set(g["nombre"].dropna().astype(str)))),
                      "metodos_enlace": " | ".join(sorted(set(c["metodo"].dropna()))), "confianza_minima": cmin,
                      "avisos_automaticos": "; ".join(avisos), "n_avisos": len(avisos), "detalle_registros": regs,
                      "correcto": "", "comentario": ""})
    return pd.DataFrame(filas).sort_values(["n_avisos", "persona_id"], ascending=[False, True])


def evaluar(ruta=None) -> dict:
    from scipy.stats import beta
    d = pd.read_csv(ruta or SALIDA / "muestra_puentes.csv", dtype=str)
    r = d["correcto"].str.strip().str.lower()
    n = int(r.isin(["si", "sí", "no"]).sum())
    k = int(r.isin(["si", "sí"]).sum())
    lo = float(beta.ppf(0.025, k, n - k + 1)) if n and k else 0.0
    return {"revisados": n, "correctos": k, "precision": k / n if n else None, "cota_inferior_95": lo,
            "cumple": lo >= 0.95, "accion": None if lo >= 0.95 else "subir a ≥ 0,85 el umbral de fusión de puentes"}


def main(evaluar_: bool = False) -> None:
    import json
    if evaluar_:
        print(json.dumps(evaluar(), ensure_ascii=False, indent=1))
        return
    from . import modelo
    tabla, _ = modelo.preparar()
    SALIDA.mkdir(parents=True, exist_ok=True)
    m = muestra(tabla)
    m.to_csv(SALIDA / "muestra_puentes.csv", index=False)
    (SALIDA / "LEEME.md").write_text(
        "# Auditoría de jugadores puente (§13)\n\n"
        f"Muestra aleatoria (semilla 20261102) de {len(m)} personas que juegan en {', '.join(LIGAS_POCOS_PUENTES)} y en "
        "otra liga. Para cada fila, comprueba que todos los registros de `detalle_registros` son la MISMA persona "
        "(ficha de la liga, fecha de nacimiento, nacionalidad, trayectoria) y escribe `sí` o `no` en `correcto` (y, si "
        "quieres, un comentario). Las filas con `avisos_automaticos` van primero.\n\n"
        "Criterio: cota inferior de Clopper-Pearson al 95 % de la precisión ≥ 0,95 (con 100 filas, como mucho 1 "
        "error). Después: `python -m bbmodel auditoria-puentes --evaluar`.\n", encoding="utf-8")
    print(f"{len(m)} personas · {int((m['n_avisos'] > 0).sum())} con avisos → {SALIDA / 'muestra_puentes.csv'}")
