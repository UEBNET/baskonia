"""F0.6 y F0.7 · Inventarios (SÓLO inventariar y proponer; nada se retira ni se mueve en la F0).

F0.6 · Residuos de «Índice Fit» y «ADAPT» (decisión 3 del CEO: se eliminan de toda vista, informe, tabla y texto; el código
de los simuladores cerrados se conserva sin tocar, sólo se deja de mostrar). Cada aparición se clasifica:
    texto_visible       cadena que el usuario lee (etiqueta, glosario, ayuda, texto comercial)
    identificador_vista identificador JS/HTML que pinta el valor (campo de datos, variable de la vista)
    codigo_cerrado      código Python de los simuladores cerrados (bbfit/…): se conserva
    documento_vigente   documento vivo (README, glosario, guía): reformular
    historico           checkpoints, encargos y CHANGELOG: registro histórico, no se toca
    datos               blobs de datos del artifact (json.gz.txt): el campo deja de leerse; regenerar en F4
y lleva su propuesta de retirada.

F0.7 · Referencias fijas al club cliente y a la temporada en el código y el artifact, con la propuesta de llevarlas a
configuración.

Salidas: data/modelos/v4_1/inventario/{fit_adapt.csv, club_temporada.csv, resumen.json}.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pandas as pd

from . import config as CE

PATRONES_FIT_ADAPT = {
    "fit_texto": re.compile(r"[ÍI]ndice\s+Fit|\bFit\b|\bFIT\b"),
    # (sin «auto-fit», «viewport-fit», «object-fit» de CSS ni «bbfit»)
    "fit_id": re.compile(r"(?<![-\w])(?:fit|fitS|indiceFit|fitrow|fitTot|fit_[A-Za-z0-9_]+|[A-Za-z0-9]+_fit)(?![-\w])"),
    "adapt_texto": re.compile(r"ADAPT%?"),
    "adapt_id": re.compile(r"\badapt_pct\w*|\bformaAdapt\b|\bcurvaAdapt\b"),
}
PATRONES_CLUB_TEMP = {
    "club": re.compile(r"[Bb]askonia|BASKONIA|Saski|Kosner|\bBKN\b"),
    "temporada": re.compile(r"\b20(?:2[0-9])-(?:2[0-9])\b"),
}
EXT = {".py", ".js", ".html", ".md", ".yaml", ".yml", ".json", ".txt", ".css"}
EXCLUIR_DIRS = {"data", "experimentos", "__pycache__", ".git", "node_modules", "_trabajo"}
MAX_BYTES = 3_000_000


def _ficheros(raiz: Path, carpetas: list[str]) -> list[Path]:
    out = []
    for c in carpetas:
        p = raiz / c
        if p.is_file():
            out.append(p)
            continue
        for f in p.rglob("*"):
            if f.is_file() and f.suffix in EXT and not (set(f.relative_to(raiz).parts) & EXCLUIR_DIRS):
                out.append(f)
    return sorted(set(out))


def _clase_fit(rel: str, termino: str, linea: str = "") -> tuple[str, str]:
    if rel.startswith("docs/checkpoints") or rel.startswith("docs/encargos") or "CHANGELOG" in rel or rel.startswith("docs/articulo"):
        return "historico", "no se toca (registro histórico)"
    if rel.endswith(".json.gz.txt") or rel.endswith(".json"):
        return "datos", "el campo deja de leerse en la vista; regenerar el blob sin él en F4"
    if rel.startswith("bbfit/") or rel.startswith("bbmodel/") or rel.startswith("bbequipo/"):
        return "codigo_cerrado", "conservar sin tocar (simulador cerrado); sólo deja de mostrarse"
    if rel.startswith("artifact/herramientas"):
        return "prueba", "actualizar la prueba de paridad/regresión en F4 al retirar la vista"
    st = linea.strip()
    if (rel.endswith(".js") or rel.endswith(".html")) and (st.startswith("*") or st.startswith("//") or st.startswith("/*")):
        return "comentario_codigo", "actualizar el comentario al retirar la vista (F4)"
    if rel.endswith(".md") or rel.endswith(".yaml"):
        return "documento_vigente", "reformular: Fit → (retirado); ADAPT% → «Landing» con su rango del 80 %"
    if termino.endswith("_texto"):
        return "texto_visible", "retirar de la vista (F4); si es adaptación, sustituir por «Landing» (decisión 4)"
    return "identificador_vista", "retirar el pintado del valor (F4); el campo de datos puede quedar sin usarse"


def inventario_fit_adapt(raiz: Path) -> pd.DataFrame:
    fs = _ficheros(raiz, ["artifact", "docs", "README.md", "CHANGELOG.md", "CONTEXTO_AGENTE.md", "bbfit", "configs"])
    filas = []
    for f in fs:
        rel = str(f.relative_to(raiz))
        if f.stat().st_size > MAX_BYTES and not rel.endswith(".json.gz.txt"):
            continue
        try:
            txt = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if rel.endswith(".json.gz.txt"):               # blob comprimido en base64: sólo se declara (no se lee el contenido)
            continue
        for i, linea in enumerate(txt.splitlines(), 1):
            for nombre, pat in PATRONES_FIT_ADAPT.items():
                for m in pat.finditer(linea):
                    tok = m.group(0)
                    if nombre == "fit_id" and tok in ("bbfit",):
                        continue
                    clase, prop = _clase_fit(rel, nombre, linea)
                    ini = max(m.start() - 60, 0)
                    filas.append({"fichero": rel, "linea": i, "metrica": nombre.split("_")[0].upper(), "patron": nombre,
                                  "token": tok, "clase": clase, "propuesta": prop,
                                  "contexto": linea[ini:m.end() + 60].strip()[:200]})
    return pd.DataFrame(filas)


def inventario_club_temporada(raiz: Path) -> pd.DataFrame:
    fs = _ficheros(raiz, ["artifact", "bbfit", "bbequipo", "bbmodel", "bbstats", "bbestilo", "configs", "ejecutar.py"])
    filas = []
    for f in fs:
        rel = str(f.relative_to(raiz))
        if f.stat().st_size > MAX_BYTES or rel.endswith(".json.gz.txt") or rel.startswith("bbequipo/ecosistema/"):
            continue
        txt = f.read_text(encoding="utf-8", errors="ignore")
        for i, linea in enumerate(txt.splitlines(), 1):
            s = linea.strip()
            if rel.endswith(".json"):
                tipo_l = "datos"
            elif rel.startswith("configs/"):
                tipo_l = "configuracion"
            elif rel.endswith(".py") and (s.startswith("#") or s.startswith('"""')):
                tipo_l = "comentario"
            else:
                tipo_l = "codigo"
            for nombre, pat in PATRONES_CLUB_TEMP.items():
                for m in pat.finditer(linea):
                    if rel.startswith("configs/"):
                        prop = "ya en configuración (verificar que sea la única fuente)"
                    elif nombre == "club":
                        prop = "mover a configs/ecosistema_v41.yaml → club_cliente (liga, club, team_id) y leerlo de ahí"
                    else:
                        prop = ("mover a configuración (temporada_actual / temporadas disponibles); derivar de "
                                "data/processed/temporadas.json")
                    filas.append({"fichero": rel, "linea": i, "tipo": nombre, "token": m.group(0), "en": tipo_l,
                                  "propuesta": {"codigo": prop, "comentario": "comentario: actualizar al mover",
                                                "datos": "dato versionado con su temporada (correcto); el lector debe elegirla por configuración",
                                                "configuracion": "ya en configuración"}[tipo_l],
                                  "contexto": linea[max(m.start() - 60, 0):m.end() + 60].strip()[:200]})
    return pd.DataFrame(filas)


def ejecutar(cfg: dict, progreso=print) -> dict:
    raiz = CE.RAIZ
    ds = CE.dir_salida(cfg, "inventario")
    fa = inventario_fit_adapt(raiz)
    ct = inventario_club_temporada(raiz)
    fa.to_csv(ds / "fit_adapt.csv", index=False)
    ct.to_csv(ds / "club_temporada.csv", index=False)
    blobs = sorted(str(p.relative_to(raiz)) for p in (raiz / "artifact").rglob("*.json.gz.txt"))
    res = {
        "version": cfg["version"], "generado": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "fit_adapt": {
            "apariciones": int(len(fa)),
            "por_clase": fa["clase"].value_counts().to_dict() if len(fa) else {},
            "por_metrica_y_clase": fa.groupby(["metrica", "clase"]).size().unstack(fill_value=0).to_dict() if len(fa) else {},
            "ficheros_vista": sorted(fa[fa["clase"].isin(["texto_visible", "identificador_vista"])]["fichero"].unique().tolist()) if len(fa) else [],
            "por_fichero_vista": fa[fa["clase"].isin(["texto_visible", "identificador_vista"])].groupby("fichero").size().to_dict() if len(fa) else {},
            "blobs_de_datos_no_inspeccionados": blobs,
        },
        "club_temporada": {
            "apariciones": int(len(ct)),
            "por_ubicacion": ct.groupby(["en", "tipo"]).size().unstack(fill_value=0).to_dict() if len(ct) else {},
            "ficheros_codigo_club": ct[(ct["en"] == "codigo") & (ct["tipo"] == "club")].groupby("fichero").size().to_dict() if len(ct) else {},
            "ficheros_codigo_temporada": ct[(ct["en"] == "codigo") & (ct["tipo"] == "temporada")].groupby("fichero").size().sort_values(ascending=False).head(30).to_dict() if len(ct) else {},
        },
    }
    (ds / "resumen.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    if progreso:
        progreso(json.dumps(res, ensure_ascii=False, indent=1)[:4000])
    return res
