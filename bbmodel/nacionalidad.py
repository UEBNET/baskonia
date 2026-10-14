"""Nacionalidad de los jugadores a partir de los datos brutos, con el mismo nombre de país en todas las ligas.

Fuentes (lo que publican las ligas; ninguna otra liga trae la nacionalidad en lo que se descarga):
  * LNB: nacionalidad de cada jugador (ficha del jugador en la API de la liga).
  * G League: país del índice de jugadores de stats.gleague.nba.com (los que siguen activos).
  * BBL: nacionalidades del máximo anotador de cada partido (sólo esos jugadores).

Propagación: la nacionalidad de una persona es la misma en todas sus filas. Se enlaza
  * por persona (persona_id del estudio de normalización, que une a un jugador entre ligas y temporadas), y
  * por (liga, player_id) entre temporadas de la misma liga.
Así un jugador de la EuroLeague que pasó por la LNB, la G League o fue máximo anotador en la BBL tiene
nacionalidad aunque la EuroLeague no la publique. La columna `nacionalidad_fuente` dice de dónde sale:
«propia» (la fila de esa liga y temporada), «misma liga» (otra temporada) u «otra liga».

    python -m bbmodel nacionalidades        →  data/modelos/nacionalidades.csv
"""
from __future__ import annotations

import glob
import gzip
import json
import re
import unicodedata
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
PROC = RAIZ / "data" / "processed"
RAW = RAIZ / "data" / "raw"
DA = RAIZ / "data" / "modelos" / "algoritmo_A" / "traducciones"
SALIDA = RAIZ / "data" / "modelos" / "nacionalidades.csv"

# Nombre en español por código ISO 3166-1 alfa-2 (los que aparecen en las fuentes)
ISO = {
    "AF": "Afganistán", "AG": "Antigua y Barbuda", "AO": "Angola", "AR": "Argentina", "AM": "Armenia", "AU": "Australia",
    "AT": "Austria", "AZ": "Azerbaiyán", "BS": "Bahamas", "BB": "Barbados", "BY": "Bielorrusia", "BE": "Bélgica",
    "BJ": "Benín", "BA": "Bosnia y Herzegovina", "BR": "Brasil", "VG": "Islas Vírgenes Británicas", "BG": "Bulgaria",
    "CM": "Camerún", "CA": "Canadá", "CF": "República Centroafricana", "CL": "Chile", "CN": "China", "CO": "Colombia",
    "CG": "Congo", "CD": "R. D. del Congo", "HR": "Croacia", "CU": "Cuba", "CZ": "Chequia", "CI": "Costa de Marfil",
    "DK": "Dinamarca", "DO": "República Dominicana", "EG": "Egipto", "ER": "Eritrea", "EE": "Estonia", "FI": "Finlandia",
    "FR": "Francia", "GA": "Gabón", "GM": "Gambia", "GE": "Georgia", "DE": "Alemania", "GH": "Ghana", "GR": "Grecia",
    "GN": "Guinea", "GY": "Guyana", "HT": "Haití", "HK": "Hong Kong", "HU": "Hungría", "IN": "India", "IR": "Irán",
    "IE": "Irlanda", "IL": "Israel", "IT": "Italia", "JM": "Jamaica", "JP": "Japón", "KE": "Kenia", "LV": "Letonia",
    "LB": "Líbano", "LR": "Liberia", "LT": "Lituania", "MG": "Madagascar", "ML": "Malí", "MX": "México",
    "ME": "Montenegro", "NL": "Países Bajos", "NZ": "Nueva Zelanda", "NI": "Nicaragua", "NG": "Nigeria",
    "MK": "Macedonia del Norte", "NO": "Noruega", "PA": "Panamá", "PL": "Polonia", "PT": "Portugal", "PR": "Puerto Rico",
    "RU": "Rusia", "SN": "Senegal", "RS": "Serbia", "SI": "Eslovenia", "ZA": "Sudáfrica", "KR": "Corea del Sur",
    "SS": "Sudán del Sur", "ES": "España", "SE": "Suecia", "CH": "Suiza", "TG": "Togo", "TT": "Trinidad y Tobago",
    "TN": "Túnez", "TR": "Turquía", "VI": "Islas Vírgenes de EE. UU.", "US": "Estados Unidos", "UG": "Uganda",
    "UA": "Ucrania", "GB": "Reino Unido", "VE": "Venezuela", "ZW": "Zimbabue", "IS": "Islandia", "QA": "Catar",
    "TD": "Chad", "TH": "Tailandia", "UY": "Uruguay", "SK": "Eslovaquia", "LU": "Luxemburgo", "CY": "Chipre",
    "PH": "Filipinas", "SY": "Siria", "JO": "Jordania", "KZ": "Kazajistán", "MD": "Moldavia", "AL": "Albania",
    "XK": "Kosovo", "DZ": "Argelia", "MA": "Marruecos", "CV": "Cabo Verde", "BF": "Burkina Faso", "SD": "Sudán",
    "ET": "Etiopía", "SO": "Somalia", "RW": "Ruanda", "BI": "Burundi", "TZ": "Tanzania", "PY": "Paraguay", "PE": "Perú",
    "EC": "Ecuador", "BO": "Bolivia", "CR": "Costa Rica", "HN": "Honduras", "SV": "El Salvador", "GT": "Guatemala",
    "BZ": "Belice", "LC": "Santa Lucía", "VC": "San Vicente y las Granadinas", "GD": "Granada", "DM": "Dominica",
    "KN": "San Cristóbal y Nieves", "BM": "Bermudas", "KY": "Islas Caimán", "TC": "Islas Turcas y Caicos",
    "SR": "Surinam", "TW": "Taiwán", "ID": "Indonesia", "MY": "Malasia", "SG": "Singapur", "VN": "Vietnam",
    "PK": "Pakistán", "IQ": "Irak", "SA": "Arabia Saudí", "AE": "Emiratos Árabes Unidos", "KW": "Kuwait",
    "BH": "Baréin", "OM": "Omán", "YE": "Yemen", "PS": "Palestina", "MN": "Mongolia", "FJ": "Fiyi",
    "PG": "Papúa Nueva Guinea", "WS": "Samoa", "TO": "Tonga", "MT": "Malta", "MC": "Mónaco", "AD": "Andorra",
    "LI": "Liechtenstein", "SM": "San Marino", "GW": "Guinea-Bisáu", "GQ": "Guinea Ecuatorial", "SL": "Sierra Leona",
    "NE": "Níger", "MR": "Mauritania", "MZ": "Mozambique", "ZM": "Zambia", "MW": "Malaui", "NA": "Namibia",
    "BW": "Botsuana", "LS": "Lesoto", "SZ": "Esuatini", "LY": "Libia",
}
# Nombres en inglés (u otras grafías) que dan las fuentes → código ISO
NOMBRES = {
    "usa": "US", "united states": "US", "united states of america": "US", "u.s.a.": "US",
    "antigua and barbuda": "AG", "bahamas": "BS", "the bahamas": "BS", "belarus": "BY", "belgium": "BE", "benin": "BJ",
    "bosnia and herzegovina": "BA", "bosnia-herzegovina": "BA", "brazil": "BR", "british virgin islands": "VG",
    "cameroon": "CM", "central african republic": "CF", "congo": "CG", "republic of the congo": "CG",
    "congo, democratic republic of the": "CD", "democratic republic of the congo": "CD", "drc": "CD", "dr congo": "CD",
    "croatia": "HR", "czech republic": "CZ", "czechia": "CZ", "cote d'ivoire": "CI", "ivory coast": "CI",
    "denmark": "DK", "dominican republic": "DO", "egypt": "EG", "finland": "FI", "france": "FR", "gabon": "GA",
    "gambia": "GM", "the gambia": "GM", "germany": "DE", "greece": "GR", "haiti": "HT", "hungary": "HU",
    "iran, islamic republic of": "IR", "iran": "IR", "ireland": "IE", "italy": "IT", "japan": "JP", "kenya": "KE",
    "latvia": "LV", "lebanon": "LB", "lithuania": "LT", "mexico": "MX", "netherlands": "NL",
    "netherlands, kingdom of the": "NL", "the netherlands": "NL", "new zealand": "NZ", "north macedonia": "MK",
    "macedonia": "MK", "norway": "NO", "poland": "PL", "russia": "RU", "russian federation": "RU", "slovenia": "SI",
    "south africa": "ZA", "south korea": "KR", "korea, republic of": "KR", "south sudan": "SS", "spain": "ES",
    "sweden": "SE", "switzerland": "CH", "trinidad and tobago": "TT", "tunisia": "TN", "turkey": "TR", "turkiye": "TR",
    "us virgin islands": "VI", "u.s. virgin islands": "VI", "virgin islands": "VI", "ukraine": "UA",
    "united kingdom": "GB", "united kingdom of great britain and northern ireland": "GB", "great britain": "GB",
    "england": "GB", "zimbabwe": "ZW", "iceland": "IS", "qatar": "QA", "thailand": "TH", "uruguay": "UY",
    "slovakia": "SK", "luxembourg": "LU", "cyprus": "CY", "philippines": "PH", "syria": "SY", "jordan": "JO",
    "kazakhstan": "KZ", "moldova": "MD", "albania": "AL", "kosovo": "XK", "algeria": "DZ", "morocco": "MA",
    "cape verde": "CV", "cabo verde": "CV", "ethiopia": "ET", "sudan": "SD", "rwanda": "RW", "peru": "PE",
    "paraguay": "PY", "ecuador": "EC", "bolivia": "BO", "costa rica": "CR", "honduras": "HN", "el salvador": "SV",
    "guatemala": "GT", "belize": "BZ", "saint lucia": "LC", "bermuda": "BM", "cayman islands": "KY", "suriname": "SR",
    "taiwan": "TW", "chinese taipei": "TW", "indonesia": "ID", "malaysia": "MY", "singapore": "SG", "vietnam": "VN",
    "pakistan": "PK", "iraq": "IQ", "saudi arabia": "SA", "united arab emirates": "AE", "palestine": "PS",
    "mongolia": "MN", "fiji": "FJ", "malta": "MT", "monaco": "MC", "andorra": "AD", "guinea-bissau": "GW",
    "equatorial guinea": "GQ", "sierra leone": "SL", "niger": "NE", "mauritania": "MR", "mozambique": "MZ",
    "zambia": "ZM", "malawi": "MW", "namibia": "NA", "botswana": "BW", "chad": "TD", "libya": "LY",
    "burkina faso": "BF", "somalia": "SO", "burundi": "BI", "tanzania": "TZ", "azerbaijan": "AZ",
    "armenia": "AM", "australia": "AU", "austria": "AT", "argentina": "AR", "angola": "AO", "chile": "CL",
}


def _llano(s: str) -> str:
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().strip()


def codigo(valor) -> str | None:
    """Código ISO alfa-2 de un país tal como lo escribe la fuente (nombre en inglés, español o código)."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    v = str(valor).strip()
    if not v:
        return None
    if len(v) == 2 and v.upper() in ISO:
        return v.upper()
    k = _llano(v)
    if k in NOMBRES:
        return NOMBRES[k]
    for c, n in ISO.items():          # ya en español
        if _llano(n) == k:
            return c
    return None


def nombre_pais(codigos: str | None) -> str | None:
    """«US» → «Estados Unidos»; «US|GH» → «Estados Unidos / Ghana»."""
    if not isinstance(codigos, str) or not codigos:
        return None
    return " / ".join(ISO.get(c, c) for c in codigos.split("|"))


def _norm_nombre(s: str) -> str:
    return re.sub(r"[^a-z]", "", _llano(s))


def _procesados() -> pd.DataFrame:
    """Filas con nacionalidad publicada por la propia liga (LNB, G League)."""
    filas = []
    for f in sorted(PROC.glob("*/ligas/*.csv")):
        d = pd.read_csv(f, usecols=lambda c: c in ("liga", "temporada", "player_id", "nombre", "nacionalidad"),
                        dtype={"player_id": str}, low_memory=False)
        if "nacionalidad" not in d:
            continue
        d = d.dropna(subset=["nacionalidad"]).drop_duplicates(["liga", "temporada", "player_id"])
        filas.append(d)
    d = pd.concat(filas, ignore_index=True) if filas else pd.DataFrame()
    d["iso"] = d["nacionalidad"].map(codigo)
    return d.dropna(subset=["iso"])[["liga", "temporada", "player_id", "iso"]]


def _bbl() -> pd.DataFrame:
    """Máximos anotadores de cada partido de la BBL (nombre + nacionalidades) enlazados con las filas procesadas
    de esa temporada por nombre (único dentro de la liga y temporada)."""
    filas = []
    for f in sorted(glob.glob(str(RAW / "bbl" / "*" / "*.json.gz"))):
        temporada = Path(f).parent.name
        try:
            d = json.load(gzip.open(f))
        except (OSError, json.JSONDecodeError):
            continue
        for g in ((d.get("payload") or {}).get("games") or {}).values():
            ts = ((g or {}).get("initialGameData") or {}).get("topScorer") or {}
            nac = [n for n in (ts.get("nationalities") or []) if n]
            if nac:
                filas.append({"temporada": temporada, "nn": _norm_nombre(f"{ts.get('firstName', '')}{ts.get('lastName', '')}"),
                              "iso": "|".join(dict.fromkeys(c.upper() for c in nac if c.upper() in ISO))})
    if not filas:
        return pd.DataFrame(columns=["liga", "temporada", "player_id", "iso"])
    t = pd.DataFrame(filas).query("iso != ''").drop_duplicates(["temporada", "nn"])
    proc = []
    for f in sorted(PROC.glob("*/ligas/bbl.csv")):
        d = pd.read_csv(f, usecols=["liga", "temporada", "player_id", "nombre"], dtype={"player_id": str}, low_memory=False)
        proc.append(d.drop_duplicates(["temporada", "player_id"]))
    p = pd.concat(proc, ignore_index=True)
    p["nn"] = p["nombre"].map(_norm_nombre)
    p = p[~p.duplicated(["temporada", "nn"], keep=False)]          # nombres ambiguos fuera
    return p.merge(t, on=["temporada", "nn"])[["liga", "temporada", "player_id", "iso"]]


def id_modelo(liga: pd.Series, player_id: pd.Series, nombre: pd.Series) -> pd.Series:
    """Identificador del jugador en el estudio de normalización: el player_id de la fuente, salvo en la BBL, cuyos
    identificadores cambian entre temporadas y se sustituyen por «n:» + nombre normalizado (bbmodel.datos)."""
    from .identidad import clave_nombre
    out = player_id.astype(str).copy()
    b = (liga == "bbl").to_numpy()
    if b.any():
        k = nombre[b].map(clave_nombre)
        out[b] = ("n:" + k.fillna("")).where(k.notna(), out[b])
    return out


def _personas() -> pd.DataFrame:
    """(liga, temporada, id del modelo) → persona_id, del estudio de normalización."""
    out = []
    for f in sorted(DA.glob("*.csv")):
        out.append(pd.read_csv(f, usecols=["persona_id", "liga", "temporada", "player_id"], dtype={"player_id": str}))
    return (pd.concat(out, ignore_index=True).drop_duplicates(["liga", "temporada", "player_id"])
            .rename(columns={"player_id": "pid_modelo"}))


def construir() -> pd.DataFrame:
    """Una fila por (liga, temporada, player_id) de todos los datos procesados, con su nacionalidad si se conoce."""
    base = []
    for f in sorted(PROC.glob("*/ligas/*.csv")):
        d = pd.read_csv(f, usecols=["liga", "temporada", "player_id", "nombre"], dtype={"player_id": str}, low_memory=False)
        base.append(d.drop_duplicates(["liga", "temporada", "player_id"]))
    base = pd.concat(base, ignore_index=True).drop_duplicates(["liga", "temporada", "player_id"])
    base["pid_modelo"] = id_modelo(base["liga"], base["player_id"], base["nombre"])
    base = base.merge(_personas(), on=["liga", "temporada", "pid_modelo"], how="left")
    obs = pd.concat([_procesados(), _bbl()], ignore_index=True).drop_duplicates(["liga", "temporada", "player_id"])
    base = base.merge(obs, on=["liga", "temporada", "player_id"], how="left")
    base["nacionalidad_fuente"] = base["iso"].notna().map({True: "propia", False: None})
    # misma liga, otra temporada (mismo jugador en la fuente)
    por_id = base.dropna(subset=["iso"]).groupby(["liga", "pid_modelo"])["iso"].agg(lambda s: s.mode().iat[0])
    falta = base["iso"].isna()
    k = pd.MultiIndex.from_frame(base.loc[falta, ["liga", "pid_modelo"]])
    v = por_id.reindex(k).to_numpy()
    base.loc[falta, "iso"] = v
    base.loc[falta & base["iso"].notna(), "nacionalidad_fuente"] = "misma liga"
    # otra liga (misma persona)
    por_persona = base.dropna(subset=["iso", "persona_id"]).groupby("persona_id")["iso"].agg(lambda s: s.mode().iat[0])
    falta = base["iso"].isna() & base["persona_id"].notna()
    base.loc[falta, "iso"] = base.loc[falta, "persona_id"].map(por_persona)
    base.loc[falta & base["iso"].notna(), "nacionalidad_fuente"] = "otra liga"
    base["nacionalidad"] = base["iso"].map(nombre_pais)
    base = base.rename(columns={"iso": "nacionalidad_iso"})
    return base[["liga", "temporada", "player_id", "pid_modelo", "persona_id", "nacionalidad", "nacionalidad_iso", "nacionalidad_fuente"]]


def main() -> Path:
    t = construir()
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    t.to_csv(SALIDA, index=False)
    cob = t.assign(con=t["nacionalidad"].notna()).groupby("liga")["con"].mean().round(3).to_dict()
    print("escrito", SALIDA, len(t), "filas; cobertura por liga:", cob)
    return SALIDA
