"""Del JSON bruto a tablas planas (CSV/JSON), resumen de indicadores y dashboard HTML autocontenido.

Las respuestas de estadísticas agrupan los valores en bloques `accumulated` (conteos), `computed`
(porcentajes, valoración...) y `advanced` (OffRtg, DefRtg, eFG%, TS%, USG%...). Se aplanan con prefijo
(`tot_`, `avg_`, `rival_tot_`...) sin descartar ningún campo, así un campo nuevo de la API aparece solo.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .extract import team_name

PTS_KEYS = ("pts", "points", "pt", "puntos")
PIR_KEYS = ("pir", "val", "valoracion")


def flatten(d: Any, prefix: str = "") -> dict:
    out: dict = {}
    if not isinstance(d, dict):
        return out
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(flatten(v, key + "."))
        elif not isinstance(v, list):
            out[key] = v
    return out


def _block(stats: Any, prefix: str) -> dict:
    """Aplana un bloque {accumulated, computed, advanced} quitando el nombre del sub-bloque."""
    out: dict = {}
    if isinstance(stats, dict):
        for sub in ("accumulated", "computed", "advanced"):
            out.update(flatten(stats.get(sub) or {}, prefix))
        rest = {k: v for k, v in stats.items()
                if k not in ("accumulated", "computed", "advanced", "name", "uuid", "dorsal")}
        out.update(flatten(rest, prefix))
    return out


def tablas(bruto: dict) -> dict[str, pd.DataFrame]:
    equipos, jugadores, partidos, box = [], [], [], []
    detalle_jug = {k: v for k, v in (bruto.get("jugadores") or {}).items() if isinstance(v, dict)}
    for uuid, item in (bruto.get("equipos") or {}).items():
        st = item.get("stats") or {}
        header = st.get("header") or {}
        season = st.get("season") or {}
        nombre = team_name(st)
        comps = header.get("competitions") or []
        base = {"team_uuid": uuid, "equipo": nombre, "propio": item.get("propio", False),
                "competicion": ", ".join(str(c.get("name", c)) if isinstance(c, dict) else str(c) for c in comps)}
        row = dict(base)
        row.update({f"cab_{k}": v for k, v in flatten(header).items() if not k.startswith("team.")})
        row.update(_block(season.get("totals"), "tot_"))
        row.update(_block(season.get("averages"), "avg_"))
        row.update(_block(season.get("opponentTotals"), "rival_tot_"))
        row.update(_block(season.get("opponentAverages"), "rival_avg_"))
        equipos.append(row)
        for p in st.get("roster") or []:
            r = {**base, "player_uuid": p.get("uuid"), "jugador": p.get("name"), "dorsal": p.get("dorsal")}
            r.update(_block(p.get("totals"), "tot_"))
            r.update(_block(p.get("averages"), "avg_"))
            det = detalle_jug.get(f"{p.get('uuid')}:{uuid}")
            if det:
                r.update(_block(((det.get("season") or {}).get("totals") or {}), "det_tot_"))
            jugadores.append(r)
        for g in st.get("games") or []:
            r = {**base}
            r.update({k: v for k, v in flatten(g).items()
                      if not k.split(".")[0] in ("accumulated", "computed", "advanced", "opponentStats")})
            r.update(_block(g, "eq_"))
            r.update(_block(g.get("opponentStats"), "rival_"))
            partidos.append(r)
    for mc, data in (bruto.get("partidos") or {}).items():
        for path, obj in _stat_rows(data):
            box.append({"matchCallUuid": mc, "bloque": path, "uuid": obj.get("uuid"),
                        "nombre": obj.get("name"), "dorsal": obj.get("dorsal"), **_block(obj, "")})
    return {"equipos": _df(equipos), "jugadores": _df(jugadores), "partidos": _df(partidos),
            "boxscores": _df(box)}


def _stat_rows(data: Any, path: str = "") -> list[tuple[str, dict]]:
    """Filas con estadísticas dentro de una respuesta de partido (cualquier objeto con `accumulated`)."""
    rows = []
    if isinstance(data, dict):
        if isinstance(data.get("accumulated"), dict) and (data.get("name") or data.get("uuid")):
            rows.append((path, data))
        for k, v in data.items():
            if k not in ("accumulated", "computed", "advanced", "playByPlay"):
                rows += _stat_rows(v, f"{path}.{k}" if path else k)
    elif isinstance(data, list):
        for v in data:
            rows += _stat_rows(v, path)
    return rows


def _df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _col(df: pd.DataFrame, prefix: str, keys: tuple) -> str | None:
    for k in keys:
        for c in (f"{prefix}{k}", f"{prefix}{k.upper()}"):
            if c in df.columns:
                return c
    return None


def resumen(t: dict[str, pd.DataFrame], bruto: dict) -> dict:
    eq, jug, par = t["equipos"], t["jugadores"], t["partidos"]
    out: dict[str, Any] = {"fecha_extraccion": bruto.get("meta", {}).get("fecha"),
                           "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                           "errores": bruto.get("meta", {}).get("errores", []),
                           "equipos": []}
    if eq.empty:
        return out
    propios = eq[eq["propio"]] if "propio" in eq else eq
    c_pts, c_pir = _col(jug, "avg_", PTS_KEYS), _col(jug, "avg_", PIR_KEYS)
    for _, e in propios.iterrows():
        u = e["team_uuid"]
        g = par[par["team_uuid"] == u] if not par.empty else par
        pf = _first_num(g, ("teamPoints", "pointsFor", "eq_pts", "eq_points"))
        pc = _first_num(g, ("opponentPoints", "pointsAgainst", "rival_pts", "rival_points"))
        ganados = int((pf > pc).sum()) if pf is not None and pc is not None else None
        j = jug[jug["team_uuid"] == u] if not jug.empty else jug
        item = {"team_uuid": u, "equipo": e.get("equipo"), "competicion": e.get("competicion"),
                "partidos": int(len(g)), "ganados": ganados,
                "perdidos": int(len(g)) - ganados if ganados is not None else None,
                "pts_favor_pp": _r(pf.mean()) if pf is not None and len(g) else None,
                "pts_contra_pp": _r(pc.mean()) if pc is not None and len(g) else None,
                "jugadores": int(len(j)), "maximos_anotadores": [], "mejor_valoracion": []}
        for col, key in ((c_pts, "maximos_anotadores"), (c_pir, "mejor_valoracion")):
            if col and not j.empty:
                top = j.assign(_v=pd.to_numeric(j[col], errors="coerce")).nlargest(5, "_v")
                item[key] = [{"jugador": r["jugador"], "valor": _r(r["_v"])} for _, r in top.iterrows()]
        out["equipos"].append(item)
    out["club"] = {"equipos": len(out["equipos"]),
                   "partidos": sum(i["partidos"] for i in out["equipos"]),
                   "ganados": sum(i["ganados"] or 0 for i in out["equipos"]),
                   "jugadores": sum(i["jugadores"] for i in out["equipos"])}
    return out


def _first_num(df: pd.DataFrame, cols: tuple) -> pd.Series | None:
    for c in cols:
        if c in df.columns:
            return pd.to_numeric(df[c], errors="coerce")
    return None


def _r(v: Any) -> Any:
    try:
        return None if pd.isna(v) else round(float(v), 2)
    except (TypeError, ValueError):
        return v


def procesar(bruto: dict, salida: Path) -> dict:
    salida.mkdir(parents=True, exist_ok=True)
    t = tablas(bruto)
    for nombre, df in t.items():
        df.to_csv(salida / f"{nombre}.csv", index=False)
        (salida / f"{nombre}.json").write_text(df.to_json(orient="records", force_ascii=False), encoding="utf-8")
    res = resumen(t, bruto)
    (salida / "resumen.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    _historico(salida, res)
    (salida / "dashboard.html").write_text(dashboard_html(res, t), encoding="utf-8")
    return res


def _historico(salida: Path, res: dict) -> None:
    """Una fila por ejecución y equipo: permite ver la evolución en el dashboard."""
    path = salida / "historico.csv"
    rows = [{"fecha_extraccion": res.get("fecha_extraccion"), **{k: v for k, v in e.items()
             if not isinstance(v, list)}} for e in res.get("equipos", [])]
    new = pd.DataFrame(rows)
    if path.exists():
        old = pd.read_csv(path)
        new = pd.concat([old[old["fecha_extraccion"] != res.get("fecha_extraccion")], new], ignore_index=True)
    new.to_csv(path, index=False)


def dashboard_html(res: dict, t: dict[str, pd.DataFrame]) -> str:
    tpl = (Path(__file__).parent / "dashboard_template.html").read_text(encoding="utf-8")
    jug = t["jugadores"]
    keep = [c for c in jug.columns if c in ("equipo", "jugador", "dorsal", "propio") or c.startswith("avg_")]
    payload = {"resumen": res,
               "jugadores": json.loads(jug[keep].to_json(orient="records", force_ascii=False)) if not jug.empty else []}
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return tpl.replace("/*__DATA__*/null", data)
