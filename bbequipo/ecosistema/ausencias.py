"""F0.5 · Auditoría de ausencias para el banco V-AUS (encargo v4.1 §4 F0.5 y §5.4). SÓLO audita: no ajusta nada.

Definición propuesta (§5.4, configs/ecosistema_v41.yaml → ausencias):
* jugador de rotación: ≥ 15 % de los minutos de su equipo en la fase regular de la temporada;
* ausente en el partido g de su equipo: 0 minutos en g, con partidos jugados (min > 0) con ese equipo ANTES y DESPUÉS de g
  (por fecha), fase regular;
* tipo: la tabla por partido NO trae el acta (las filas jugo = False están imputadas entre la primera y la última aparición
  del jugador), así que «decisión técnica» frente a «lesión» no es observable. Indicio [HIPÓTESIS]: ausencia aislada
  (1 partido) frente a racha (≥ 2 partidos consecutivos);
* los partidos con más de un ausente de rotación se cuentan aparte (en F3 el CEO decide excluirlos o tratarlos como
  escenario de varias bajas).

Fuente: data/modelos/roles/partidos_jugador/<t>.csv.gz (una fila por jugador y partido del acta, desde el jugada a jugada;
las ligas sin PBP no figuran). Cobertura de tramos: inventario del contrato v4.0.

Diagnósticos de endogeneidad (§5.4, declarados):
* tramo final de la temporada regular (último 15 % de las fechas del equipo): tasa de ausencia frente al resto (descansos
  en partidos sin nada en juego);
* carga previa: minutos del ausente en su partido anterior frente a su media (lesión tras sobrecarga).

Salidas: data/modelos/v4_1/ausencias/{auditoria_liga_temporada.csv, ausencias.csv.gz, resumen.json}.
"""
from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd

from . import config as CE

COLS = ["liga", "temporada", "game_id", "fase", "team_id", "player_id", "persona_id", "jugo", "min", "fecha"]


def _tabla(temp: str) -> pd.DataFrame | None:
    p = CE.RAIZ / "data/modelos/roles/partidos_jugador" / f"{temp}.csv.gz"
    if not p.exists():
        return None
    d = pd.read_csv(p, usecols=COLS, low_memory=False)
    d["jugo"] = d["jugo"].astype(str).str.lower().isin(["true", "1"])
    d["min"] = pd.to_numeric(d["min"], errors="coerce").fillna(0.0)
    d["fecha"] = pd.to_datetime(d["fecha"], errors="coerce")
    d["game_id"] = d["game_id"].astype(str)
    d["team_id"] = d["team_id"].astype(str)
    d["player_id"] = d["player_id"].astype(str)
    return d


def ausencias_liga_temporada(d: pd.DataFrame, cfg_a: dict, umbral: float) -> tuple[pd.DataFrame, dict]:
    """Ausencias de jugadores de rotación en una liga-temporada (fase regular). `umbral`: cuota mínima de los minutos
    TOTALES de jugador del equipo (Σ = 1; literal del §5.4: 0,15 ≈ 30 min por partido de 40')."""
    d = d[d["fase"] == cfg_a.get("fase", "regular")]
    info = {"partidos_box": int(d["game_id"].nunique()), "filas": int(len(d))}
    if d.empty:
        return pd.DataFrame(), info
    # partidos de cada equipo (calendario) y minutos de cada jugador con su equipo
    pe = d.groupby(["team_id", "game_id"], as_index=False)["fecha"].first().sort_values(["team_id", "fecha", "game_id"])
    pe["orden"] = pe.groupby("team_id").cumcount()
    pe["n_eq"] = pe.groupby("team_id")["orden"].transform("size")
    pe["final"] = pe["orden"] >= np.floor(0.85 * pe["n_eq"])
    min_eq = d.groupby("team_id")["min"].sum()
    mj = d.groupby(["team_id", "player_id"]).agg(min_tot=("min", "sum"), persona_id=("persona_id", "first")).reset_index()
    mj["cuota"] = mj["min_tot"] / mj["team_id"].map(min_eq) * 5.0      # cuota de los minutos de un puesto (Σ = 5)
    mj["cuota_min_equipo"] = mj["min_tot"] / mj["team_id"].map(min_eq)  # cuota de los minutos totales del equipo (Σ = 1)
    rot = mj[mj["cuota_min_equipo"] >= float(umbral)]
    info["jugadores_rotacion"] = int(len(rot))
    # rejilla jugador de rotación × partido de su equipo
    g = rot[["team_id", "player_id", "persona_id", "cuota", "cuota_min_equipo"]].merge(pe, on="team_id")
    j = d[["team_id", "game_id", "player_id", "jugo", "min"]]
    g = g.merge(j, on=["team_id", "game_id", "player_id"], how="left")
    g["en_acta"] = g["jugo"].notna()
    g["min"] = g["min"].fillna(0.0)
    jugado = g["min"] > 0
    g["o_jug"] = np.where(jugado, g["orden"], np.nan)
    gg = g.groupby(["team_id", "player_id"])["o_jug"]
    g["primero"], g["ultimo"] = gg.transform("min"), gg.transform("max")
    aus = g[(~jugado) & (g["orden"] > g["primero"]) & (g["orden"] < g["ultimo"])].copy()
    # [DATO 06-11-2026] la tabla por partido rellena con jugo = False los partidos del equipo entre la primera y la última
    # aparición del jugador en los tramos (bbfit.roles.partidos_jugador): «en acta» NO es observable con ella. Se usa como
    # indicio la longitud del episodio (racha de partidos consecutivos sin jugar): 1 partido ≈ descanso o decisión técnica;
    # ≥ 2 ≈ lesión o baja [HIPÓTESIS].
    aus = aus.sort_values(["team_id", "player_id", "orden"])
    nuevo = aus.groupby(["team_id", "player_id"])["orden"].diff().ne(1)
    aus["episodio"] = nuevo.cumsum()
    aus["long_episodio"] = aus.groupby("episodio")["orden"].transform("size")
    aus["tipo"] = np.where(aus["long_episodio"] == 1, "aislada_1_partido", "racha_2_o_mas")
    # carga previa: minutos en el último partido JUGADO antes del episodio frente a la media del jugador
    jg = g[jugado][["team_id", "player_id", "orden", "min"]].sort_values("orden")
    ini = aus.groupby("episodio").agg(team_id=("team_id", "first"), player_id=("player_id", "first"),
                                      orden=("orden", "min")).reset_index().sort_values("orden")
    prev = pd.merge_asof(ini, jg.rename(columns={"min": "min_prev"}), on="orden", by=["team_id", "player_id"],
                         allow_exact_matches=False, direction="backward")
    aus = aus.merge(prev[["episodio", "min_prev"]], on="episodio", how="left")
    med = g[jugado].groupby(["team_id", "player_id"])["min"].mean().rename("min_medio")
    aus = aus.merge(med.reset_index(), on=["team_id", "player_id"], how="left")
    n_aus = aus.groupby(["team_id", "game_id"]).size().rename("ausentes_rotacion_en_partido")
    aus = aus.merge(n_aus.reset_index(), on=["team_id", "game_id"], how="left")
    # tasas
    elegibles = g[(g["orden"] > g["primero"]) & (g["orden"] < g["ultimo"])]
    info.update({
        "equipo_partidos": int(len(pe)),
        "jugador_partidos_elegibles": int(len(elegibles)),
        "ausencias": int(len(aus)),
        "tasa_ausencia": float(len(aus) / max(len(elegibles), 1)),
        "equipo_partidos_con_ausente": int(n_aus.size),
        "equipo_partidos_un_ausente": int((n_aus == 1).sum()),
        "equipo_partidos_varios_ausentes": int((n_aus > 1).sum()),
        "frac_aisladas_1_partido": float((aus["tipo"] == "aislada_1_partido").mean()) if len(aus) else np.nan,
        "episodios": int(aus["episodio"].nunique()) if len(aus) else 0,
        "tasa_ausencia_tramo_final": float(aus["final"].sum() / max(elegibles["final"].sum(), 1)),
        "tasa_ausencia_resto": float((~aus["final"]).sum() / max((~elegibles["final"]).sum(), 1)),
        "carga_previa_ratio_mediana": float(np.nanmedian(aus["min_prev"] / aus["min_medio"])) if len(aus) else np.nan,
    })
    return aus, info


def ejecutar(cfg: dict, progreso=print) -> dict:
    cfg_a = cfg["ausencias"]
    cfg40 = CE.cargar_v40(cfg)
    inv = pd.read_csv(CE.RAIZ / cfg40["salida"] / "contrato" / "inventario_tramos.csv")
    temps = cfg["orden_sinergias"]["temporadas"]
    umbrales = [float(cfg_a["rotacion_min_cuota_minutos"])] + [float(u) for u in cfg_a.get("umbrales_alternativos", [])]
    filas, todas = [], []
    for t in temps:
        d = _tabla(t)
        if d is None:
            continue
        for (liga, dl), umb in ((par, u) for par in d.groupby("liga") for u in umbrales):
            aus, info = ausencias_liga_temporada(dl, cfg_a, umb)
            info["umbral"] = umb
            iv = inv[(inv["liga"] == liga) & (inv["temporada"] == t)]
            info.update({"liga": liga, "temporada": t,
                         "partidos_total_liga": int(iv["partidos_total"].iloc[0]) if len(iv) else np.nan,
                         "frac_partidos_con_quintetos": float(iv["fraccion_partidos_con_quintetos"].iloc[0]) if len(iv) else np.nan,
                         "decision_contrato_v40": str(iv["decision"].iloc[0]) if len(iv) else "sin_tramos"})
            info["cobertura_box"] = (info["partidos_box"] / info["partidos_total_liga"]
                                     if info.get("partidos_total_liga") and info["partidos_total_liga"] > 0 else np.nan)
            filas.append(info)
            if len(aus):
                aus["liga"], aus["temporada"], aus["umbral"] = liga, t, umb
                todas.append(aus)
        if progreso:
            progreso(f"  ausencias {t}: {sum(1 for f in filas if f['temporada'] == t)} ligas×umbral", flush=True)
    tab = pd.DataFrame(filas)
    cols = ["umbral", "liga", "temporada", "decision_contrato_v40", "partidos_total_liga", "partidos_box", "cobertura_box",
            "frac_partidos_con_quintetos", "jugadores_rotacion", "equipo_partidos",
            "jugador_partidos_elegibles", "ausencias", "tasa_ausencia", "equipo_partidos_con_ausente",
            "equipo_partidos_un_ausente", "equipo_partidos_varios_ausentes", "episodios", "frac_aisladas_1_partido",
            "tasa_ausencia_tramo_final", "tasa_ausencia_resto", "carga_previa_ratio_mediana"]
    tab = tab[[c for c in cols if c in tab.columns]].sort_values(["umbral", "liga", "temporada"])
    ds = CE.dir_salida(cfg, "ausencias")
    tab.to_csv(ds / "auditoria_liga_temporada.csv", index=False, float_format="%.4f")
    A = pd.concat(todas, ignore_index=True) if todas else pd.DataFrame()
    if len(A):
        A[["umbral", "liga", "temporada", "team_id", "game_id", "player_id", "persona_id", "cuota_min_equipo", "tipo", "long_episodio", "final",
           "min_prev", "min_medio", "ausentes_rotacion_en_partido"]].to_csv(ds / "ausencias.csv.gz", index=False)
    elite = set(cfg["comunes"]["segmentos"]["elite_club"])

    def agg(t: pd.DataFrame) -> dict:
        un = t["equipo_partidos_un_ausente"].sum()
        return {"ligas_temporada": int(len(t)), "ausencias": int(t["ausencias"].sum()),
                "equipo_partidos_un_ausente": int(un), "equipo_partidos_varios_ausentes": int(t["equipo_partidos_varios_ausentes"].sum()),
                "tasa_ausencia_media": float(np.average(t["tasa_ausencia"], weights=t["jugador_partidos_elegibles"])),
                "frac_aisladas_1_partido": float(np.nansum(t["frac_aisladas_1_partido"] * t["ausencias"]) / max(t["ausencias"].sum(), 1)),
                "tasa_tramo_final_sobre_resto": float(np.nansum(t["tasa_ausencia_tramo_final"] * t["jugador_partidos_elegibles"]) /
                                                       np.nansum(t["tasa_ausencia_resto"] * t["jugador_partidos_elegibles"])),
                "con_tramos_contrato": int((t["decision_contrato_v40"].isin(["incluida", "incluida_con_aviso"])).sum())}
    res = {"version": cfg["version"], "generado": time.strftime("%Y-%m-%dT%H:%M:%S"), "definicion": cfg_a, "por_umbral": {}}
    for umb in umbrales:
        tu = tab[tab["umbral"] == umb]
        r = {"min_por_partido_fiba_aprox": round(umb * 200, 1), "global": agg(tu), "elite_club": agg(tu[tu["liga"].isin(elite)])}
        if len(A):
            Au = A[A["umbral"] == umb]
            a1 = Au[Au["ausentes_rotacion_en_partido"] == 1]
            r["un_ausente_por_tipo"] = a1["tipo"].value_counts().to_dict()
            r["un_ausente_por_tipo_elite"] = a1[a1["liga"].isin(elite)]["tipo"].value_counts().to_dict()
            r["carga_previa_ratio_mediana"] = float(np.nanmedian(Au["min_prev"] / Au["min_medio"]))
        res["por_umbral"][str(umb)] = r
    (ds / "resumen.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    if progreso:
        progreso(json.dumps(res["por_umbral"], ensure_ascii=False, indent=1, default=float))
    return res
