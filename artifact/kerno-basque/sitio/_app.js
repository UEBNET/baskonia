/* =====================================================================================================
   Kerno Basque Analytics · Equipos
   Misma tipología que «Kerno Analytics · Equipos» (contexto único, raíl 01–04, herramientas de detalle e informe en
   PDF) sobre las cuatro ligas masculinas de la Federación Vasca: Primera y Segunda Nacional, Junior y Cadete.
   Datos: python -m bbstats.esf kerno (bbstats/esf/kerno.py) → quintetos/datos, atlas/estilos y datos/kerno.
   Lo que no está: simulador de fichajes, modelo multiliga v4.0 y vara entre ligas (no hay puente de normalización
   entre las ligas vascas y las profesionales). El Nivel Kerno se mide dentro de cada liga vasca y temporada.
   ===================================================================================================== */
"use strict";
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const LS = {
  get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* sin almacenamiento */ } },
  json(k, d) { try { const v = JSON.parse(localStorage.getItem(k)); return v == null ? d : v; } catch (e) { return d; } },
};
const norm = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const ok = (v) => typeof v === "number" && isFinite(v);
const fmt = (v, d = 1) => { if (v == null || !isFinite(v)) return "—"; const f = Math.pow(10, d), x = Math.round(v * f) / f; return (x === 0 ? 0 : x).toLocaleString("es-ES", { minimumFractionDigits: d, maximumFractionDigits: d }).replace("-", "−"); };
const sgn = (v, d = 1) => { const t = fmt(v, d); return t !== "—" && Math.round(v * Math.pow(10, d)) > 0 ? "+" + t : t; };
const ord = (n) => `${n}.º`;
const rngTxt = (a, b) => (/[−+]/.test(a + b) ? `${a} – ${b}` : `${a}–${b}`);
const bombOK = (s) => /^[ -~À-ÞŁŒŠŸŽ]*$/.test(String(s || "").toLocaleUpperCase("es"));
const U = (z) => 50 + 50 * Math.tanh(z / 2);   // escala 0–100 del sitio (73 = una desviación típica por encima)

// ---------------------------------------------------------------------------------------------- datos
async function jsonDe(r) {
  const txt = (await r.text()).trim();
  if (!txt.startsWith("H4sI")) return JSON.parse(txt);
  const bin = atob(txt), u8 = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
  return JSON.parse(await new Response(new Blob([u8]).stream().pipeThrough(new DecompressionStream("gzip"))).text());
}
async function cargarJSON(path) {
  try { const r = await fetch(path + ".gz.txt"); if (r.ok) return await jsonDe(r); } catch (e) { /* sin versión comprimida */ }
  const r = await fetch(path); if (!r.ok) throw new Error(`${path} (${r.status})`); return jsonDe(r);
}
const LIGAS = ["esf_1nac", "esf_2nac", "esf_jun", "esf_cad"];
const LIGA_N = { esf_1nac: "Primera Nacional", esf_2nac: "Segunda Nacional", esf_jun: "Junior · Liga Vasca", esf_cad: "Cadete · Liga Vasca" };
const LIGA_C = { esf_1nac: "1ª Nacional", esf_2nac: "2ª Nacional", esf_jun: "Junior", esf_cad: "Cadete" };
const ligaN = (l) => LIGA_N[l] || String(l || "");
const ligaOrd = (a, b) => (LIGAS.indexOf(a) + 1 || 99) - (LIGAS.indexOf(b) + 1 || 99);
const POS = { E: "Exterior", A: "Alero", I: "Interior" }, POSP = { E: "exteriores", A: "aleros", I: "interiores" };
const EST_COL = ["#2B6FBF", "#D35C2A", "#12997A", "#6550CC", "#CC6390", "#7F8418"];   // paleta categórica de marca, mismo orden que «Equipos y quintetos»
let ESTILOS = [];   // los seis estilos (taxonomía unificada): id, nombre, definición, equipo, jugador, rol, centroide

// métricas de la ficha y de la comparativa (todas en su liga y temporada: percentil entre los jugadores con 100+ min)
const M = {
  NK: { n: "Nivel Kerno", d: 0 }, PROD: { n: "Producción", d: 0 }, IMP: { n: "Impacto", d: 0 },
  per: { n: "PER", c: "PER", d: 1 }, ws_per_40: { n: "Win shares por 40′", c: "win shares", d: 3 }, gs40: { n: "Game score por 40′", c: "game score", d: 1 },
  rapm: { n: "RAPM (pts/100)", c: "RAPM", d: 1, sg: 1 }, onoff: { n: "On/off ajustado (pts/100)", c: "on/off", d: 1, sg: 1 },
  ortg: { n: "Rating ofensivo", d: 1 }, drtg: { n: "Rating defensivo", c: "rating defensivo", d: 1 },
  pts_p100: { n: "Puntos por 100 posesiones", c: "volumen de puntos", d: 1 }, ts_pct: { n: "Tiro verdadero (TS%)", c: "eficiencia de tiro (TS%)", d: 1, pc: 1 },
  fg2_pct: { n: "Acierto en tiros de 2", c: "acierto en tiros de 2", d: 1, pc: 1 }, fg3_pct: { n: "Acierto en triples", c: "acierto en triples", d: 1, pc: 1 },
  ft_pct: { n: "Acierto en tiros libres", c: "tiros libres", d: 1, pc: 1 }, fta_rate: { n: "Tiros libres por tiro de campo", c: "llegada a la línea de tiros libres", d: 1, pc: 1 },
  fg3a_rate: { n: "Proporción de triples", d: 1, pc: 1 }, usg_pct: { n: "Uso", d: 1, pc: 1 },
  ast_pct: { n: "Asistencias (AST%)", c: "asistencias", d: 1, pc: 1 }, tov_pct: { n: "Pérdidas (TOV%)", c: "cuidado del balón (pocas pérdidas)", d: 1, pc: 1 },
  oreb_pct: { n: "Rebote ofensivo (OREB%)", c: "rebote ofensivo", d: 1, pc: 1 }, dreb_pct: { n: "Rebote defensivo (DREB%)", c: "rebote defensivo", d: 1, pc: 1 },
  stl_pct: { n: "Robos (STL%)", c: "robos", d: 1, pc: 1 }, blk_pct: { n: "Tapones (BLK%)", c: "tapones", d: 1, pc: 1 }, pf_p100: { n: "Faltas por 100 posesiones", c: "control de faltas", d: 1 },
  pct_aro: { n: "Tiros en el aro", d: 1, pc: 1 }, pct_corta: { n: "Tiros cortos", d: 1, pc: 1 }, pct_media: { n: "Media distancia", d: 1, pc: 1 },
  pct_t3_esquina: { n: "Triples de esquina", d: 1, pc: 1 },
};
const SENT = { drtg: -1, tov_pct: -1, pf_p100: -1, usg_pct: 0, fg3a_rate: 0, pct_aro: 0, pct_corta: 0, pct_media: 0, pct_t3_esquina: 0 };
const GRUPOS = [
  ["Valor", "Producción por minuto e impacto en el marcador", ["per", "ws_per_40", "gs40", "rapm", "onoff"]],
  ["Anotación", "Volumen y eficiencia", ["pts_p100", "ts_pct", "fg2_pct", "fg3_pct", "ft_pct", "fta_rate"]],
  ["Creación y cuidado del balón", "Asistencias: solo donde la mesa las registra (2026-27)", ["ast_pct", "tov_pct"]],
  ["Rebote", "", ["oreb_pct", "dreb_pct"]],
  ["Defensa", "Tapones: solo donde la mesa los registra", ["stl_pct", "blk_pct", "drtg", "pf_p100"]],
  ["Perfil de juego", "Volumen y estilo: no hay mejor ni peor", ["usg_pct", "fg3a_rate", "pct_aro", "pct_corta", "pct_media", "pct_t3_esquina"]],
];

let IDX = null, EQ = null, EUC = null, TEMPS = [];
const SEAS = {}, PEND = {};
function temporada(t) {
  if (SEAS[t]) return Promise.resolve(SEAS[t]);
  if (PEND[t]) return PEND[t];
  PEND[t] = cargarJSON(`datos/kerno/${t}.json`).then((d) => {
    const C = d.columnas, rows = d.filas.map((f) => { const o = {}; C.forEach((c, i) => { o[c] = f[i]; }); return o; });
    const T = { temp: t, rows, ref: {} };
    rows.forEach((r) => { r.T = T; r.k = `${t}|${r.player_id}|${r.team_id}`; });
    T.byKey = new Map(rows.map((r) => [r.k, r]));
    SEAS[t] = T; return T;
  }).catch((e) => { delete PEND[t]; throw e; });
  return PEND[t];
}
const porClave = (k) => { const t = String(k || "").split("|")[0]; return SEAS[t] ? SEAS[t].byKey.get(k) || null : null; };
function ecdf(a, v) {
  if (!a || !a.length || !ok(v)) return null;
  let lo = 0, hi = a.length; while (lo < hi) { const m = (lo + hi) >> 1; if (a[m] < v) lo = m + 1; else hi = m; }
  let le = lo; while (le < a.length && a[le] === v) le++;
  return (100 * (lo + (le - lo) / 2)) / a.length;
}
function refDe(T, liga, m) {
  const k = `${liga}|${m}`; if (T.ref[k]) return T.ref[k];
  let a = T.rows.filter((r) => r.liga === liga && (r.min || 0) >= 100 && ok(r[m])).map((r) => r[m]);
  if (a.length < 15) a = T.rows.filter((r) => r.liga === liga && (r.min || 0) >= 30 && ok(r[m])).map((r) => r[m]);
  a.sort((x, y) => x - y); return (T.ref[k] = a);
}
// estimación de una métrica: punto, rango (si existe) y percentil en su liga (en el sentido favorable cuando lo hay)
function est(r, m) {
  if (!r) return null;
  if (m === "NK" || m === "IMP" || m === "PROD") {
    const k = { NK: "nk", IMP: "imp", PROD: "prod" }[m], v = r[k]; if (!ok(v)) return null;
    const lo = k === "prod" ? v : r[k + "_lo"], hi = k === "prod" ? v : r[k + "_hi"];
    return { m, v, lo, hi, p: v, pl: Math.min(lo ?? v, v), ph: Math.max(hi ?? v, v), s: 1, w: (hi ?? v) - (lo ?? v) };
  }
  const v = r[m]; if (!ok(v)) return null;
  const s = SENT[m] ?? 1; let p = ecdf(refDe(r.T, r.liga, m), v); if (p == null) return null;
  if (s === -1) p = 100 - p;
  return { m, v, lo: null, hi: null, p, pl: p, ph: p, s, w: 0 };
}
const fmtM = (m, v) => { const k = M[m] || { d: 1 }; return k.sg ? sgn(v, k.d) : fmt(v, k.d); };
const valHTML = (e, completo = false) => {
  if (!e) return "—";
  const v = `${fmtM(e.m, e.v)}${M[e.m] && M[e.m].pc ? " %" : ""}`;
  if (ok(e.lo) && ok(e.hi) && e.hi > e.lo) { const r = rngTxt(fmtM(e.m, e.lo), fmtM(e.m, e.hi)); return completo ? `<b>${v}</b> <span class="rng">[${r}]</span>` : `<b title="Rango del 80 %: ${r}">${v}</b>`; }
  return completo ? `<b>${v}</b> <span class="rng">p${Math.round(e.p)}</span>` : `<b>${v}</b>`;
};
const tier = (e) => (!e ? "" : e.s === 0 ? "t-neu" : e.p >= 60 ? "t-hi" : e.p <= 40 ? "t-lo" : "t-mid");
const pbar = (e, completo = false) => (e ? `<div class="pbar ${tier(e)}" role="img" aria-label="${Math.round(e.p)} de 100${e.ph > e.pl ? `, rango ${Math.round(e.pl)}–${Math.round(e.ph)}` : ""}">${completo && e.ph > e.pl ? `<span class="b" style="left:${e.pl.toFixed(1)}%;width:${Math.max(0.6, e.ph - e.pl).toFixed(1)}%"></span>` : ""}<span class="p" style="left:${Math.max(0, Math.min(100, e.p)).toFixed(1)}%"></span></div>` : `<div class="pbar"></div>`);
const nkbar = (v, lo, hi) => (ok(v) ? `<div class="nkbar ${v >= 60 ? "hi" : v <= 40 ? "lo" : ""}" role="img" aria-label="Nivel Kerno ${Math.round(v)}${ok(lo) ? `, rango ${Math.round(lo)}–${Math.round(hi)}` : ""}">${ok(lo) && ok(hi) ? `<span class="b" style="left:${lo.toFixed(1)}%;width:${Math.max(0.6, hi - lo).toFixed(1)}%"></span>` : ""}<span class="p" style="left:${v.toFixed(1)}%"></span></div>` : "");
const nivelTxt = (x) => (x >= 75 ? "muy alto" : x >= 60 ? "alto" : x >= 40 ? "medio" : x >= 25 ? "bajo" : "muy bajo");
const confTxt = (r) => { const w = (r.nk_hi ?? 0) - (r.nk_lo ?? 0); return w <= 25 ? "alta" : w <= 45 ? "moderada" : "baja"; };
const confHTML = (r) => { const c = confTxt(r); return `<span class="conf ${c}" title="Rango del 80 % del Nivel Kerno: ${Math.round(r.nk_lo)}–${Math.round(r.nk_hi)}"><i><span></span></i>${c}</span>`; };

// equipos (totales, plantillas, entrenadores) y estilos de club
function equipos() {
  if (EQ) return Promise.resolve(EQ);
  return cargarJSON("quintetos/datos/equipos").then((d) => {
    const C = d.columnas; d.F = d.filas.map((f) => { const o = {}; C.forEach((c, i) => { o[c] = f[i]; }); return o; });
    d.F.forEach((r) => { const p = d.plantillas[r.k]; r.L = p && ok(p.L) ? p.L : null; });
    EQ = d; return d;
  });
}
function estilosClubes() { if (EUC) return Promise.resolve(EUC); return cargarJSON("quintetos/estilos_unificados_clubes").then((d) => { EUC = d; ESTILOS = d.estilos || ESTILOS; return d; }).catch(() => null); }
const eqFilas = (t, liga) => (EQ ? EQ.F.filter((r) => r.t === t && r.liga === liga && r.f === "regular") : []);
const eqFila = (t, liga, id) => (EQ ? EQ.F.find((r) => r.t === t && r.liga === liga && r.f === "regular" && r.id === id) || null : null);
const clubInfo = (t, liga, id) => (EQ && EQ.clubes[`${liga}:${id}:${t}`]) || null;
function clubes(t) {
  const out = []; if (!EQ) return out;
  EQ.F.forEach((r) => { if (r.t === t && r.f === "regular") out.push({ liga: r.liga, id: r.id, nombre: r.eq, div: (clubInfo(t, r.liga, r.id) || {}).division }); });
  return out.sort((a, b) => ligaOrd(a.liga, b.liga) || a.nombre.localeCompare(b.nombre, "es"));
}
const clubActual = () => clubes(CTX.temp).find((c) => c.liga === CTX.liga && c.id === CTX.id) || null;
// nivel de la plantilla en 0–100: 50 = club medio de su liga en esa temporada (media del nivel de sus plantillas)
function nivelPlantilla(t, liga, L) {
  if (!ok(L)) return null; const v = eqFilas(t, liga).map((r) => r.L).filter(ok); if (!v.length) return null;
  const m = v.reduce((a, b) => a + b, 0) / v.length; return U(L - m);
}
function etapasClub(liga, id) {
  const pre = `${liga}:${id}:`, out = [];
  if (!EQ) return out;
  for (const [k, c] of Object.entries(EQ.clubes)) { if (!k.startsWith(pre)) continue; const t = k.slice(pre.length); (c.ent || []).forEach((e) => out.push(Object.assign({}, e, { temp: t, L: (EQ.plantillas[k] || {}).L }))); }
  return out.sort((a, b) => a.temp.localeCompare(b.temp) || String(a.de).localeCompare(String(b.de)));
}
function entrenadores(liga, id) {
  const m = new Map();
  etapasClub(liga, id).forEach((e) => { const o = m.get(e.id) || { id: e.id, n: e.n, et: [] }; o.et.push(e); m.set(e.id, o); });
  return [...m.values()].map((o) => Object.assign(o, { pri: o.et[0].temp, ult: o.et[o.et.length - 1].temp })).sort((a, b) => b.ult.localeCompare(a.ult) || String(a.n).localeCompare(String(b.n), "es"));
}
const entActual = () => (CTX.ent && EQ ? entrenadores(CTX.liga, CTX.id).find((o) => o.id === CTX.ent) || null : null);
const estiloClub = (t, liga, id) => { const c = EUC && EUC.c && EUC.c[`${liga}:${id}:${t}`]; return c && c.u ? c : null; };
const MES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const fecha = (x) => { if (!x) return "—"; const [y, m, d] = String(x).split("-"); return `${+d} ${MES[+m - 1]} ${y}`; };

// ---------------------------------------------------------------------------------------------- contexto único
const hoy = new Date();
const enCurso = (t) => { const y = +String(t).slice(0, 4); return hoy < new Date(y + 1, 6, 1) && hoy >= new Date(y, 7, 1); };
const CTX = Object.assign({ temp: null, liga: "esf_jun", id: "", ent: "", escala: "escala", ayudas: true, tema: "sistema" }, LS.json("kb.ctx", {}));
const guardarCtx = () => LS.set("kb.ctx", JSON.stringify(CTX));
const temaResuelto = () => (CTX.tema === "light" || CTX.tema === "dark" ? CTX.tema : matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
function aplicarTema() {
  if (CTX.tema === "light" || CTX.tema === "dark") document.documentElement.dataset.theme = CTX.tema; else delete document.documentElement.dataset.theme;
  LS.set("cerno.v2.tema", CTX.tema); LS.set("mm.theme", temaResuelto());
}
function pintarCtx() {
  $("ctxTemp").innerHTML = TEMPS.map((t) => `<option value="${t}">${t}${enCurso(t) ? " · en curso" : ""}</option>`).join("");
  $("ctxTemp").value = CTX.temp;
  const cs = clubes(CTX.temp), grupos = {};
  cs.forEach((c) => { (grupos[c.liga] = grupos[c.liga] || []).push(c); });
  $("ctxClub").innerHTML = Object.keys(grupos).sort(ligaOrd).map((l) => `<optgroup label="${esc(ligaN(l))}">${grupos[l].map((c) => `<option value="${esc(c.liga + "|" + c.id)}">${esc(c.nombre)}${c.div && c.div !== "única" ? ` · ${esc(c.div)}` : ""}</option>`).join("")}</optgroup>`).join("");
  if (!cs.some((c) => c.liga === CTX.liga && c.id === CTX.id)) {
    const b = cs.find((c) => c.liga === CTX.liga && c.id.startsWith(CTX.id.split("-")[0] || "~")) || cs.find((c) => c.liga === "esf_jun" && /baskonia/.test(c.id)) || cs.find((c) => /baskonia/.test(c.id)) || cs[0];
    if (b) { CTX.liga = b.liga; CTX.id = b.id; guardarCtx(); }
  }
  $("ctxClub").value = CTX.liga + "|" + CTX.id;
  $("varaTxt").textContent = LIGA_C[CTX.liga] || "liga";
  marcarAplica();
}
function pintarEnt() {
  const el = $("ctxEnt"); if (!el) return;
  if (!EQ) { el.innerHTML = `<option value="">Cargando…</option>`; el.disabled = true; return; }
  const es = entrenadores(CTX.liga, CTX.id); el.disabled = !es.length;
  if (CTX.ent && !es.some((o) => o.id === CTX.ent)) { CTX.ent = ""; guardarCtx(); }
  const enT = new Set(etapasClub(CTX.liga, CTX.id).filter((e) => e.temp === CTX.temp).map((e) => e.id));
  el.innerHTML = `<option value="">${es.length ? `Todos (${es.length})` : "Sin datos"}</option>` + es.map((o) => `<option value="${esc(o.id)}">${esc(o.n)} · ${o.pri === o.ult ? o.pri : `${o.pri.slice(0, 4)}–${o.ult.slice(5)}`}${enT.has(o.id) ? " · en esta temporada" : ""}</option>`).join("");
  el.value = CTX.ent || "";
}
function pintarAjustes() {
  const marca = (id, v) => $(id).querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.v === v)));
  marca("setEsc", CTX.escala); marca("setAyu", CTX.ayudas ? "1" : "0"); marca("setTema", CTX.tema);
}
// lo que se comparte con las herramientas de detalle (mismo origen: almacenamiento local + mensaje al marco)
function publicarCtx() {
  const c = { temp: CTX.temp, vara: CTX.liga, escala: CTX.escala, ayudas: CTX.ayudas, tema: temaResuelto(), club: { liga: CTX.liga, id: CTX.id, temp: CTX.temp }, stamp: Date.now() };
  LS.set("cerno.ctx", JSON.stringify(c)); LS.set("mm.escala", CTX.escala); LS.set("kb.vara", CTX.liga);
  const P = (fr, m) => { try { if (fr && fr.dataset.listo) fr.contentWindow.postMessage(m, "*"); } catch (e) { /* */ } };
  P(FR.a, { cernoCtx: c }); P(FR.a, { escala: CTX.escala });
  P(FR.q, { tema: c.tema }); P(FR.q, { escala: CTX.escala }); P(FR.q, { aprende: !!CTX.ayudas });
}

// ---------------------------------------------------------------------------------------------- flujo y navegación
// [id, nombre, destino]: q = pestaña de «Equipos y quintetos», a = pestaña del Atlas, f = vista de la Federación; sin destino, vista propia
const NAV = [
  { t: "Lectura", items: [["inicio", "Tu equipo hoy"]] },
  { n: "01", t: "Diagnóstico", q: "¿Cómo está mi equipo?", items: [
    ["eq-evaluacion", "Evaluación", { q: "evaluacion" }], ["eq-rotacion", "Rotación", { q: "equipo" }], ["eq-quintetos", "Quintetos", { q: "quintetos" }],
    ["eq-parejas", "Parejas y tríos", { q: "parejas" }], ["eq-conexiones", "Conexiones", { q: "conexiones" }], ["eq-impacto", "Impacto en pista", { q: "jugadores" }],
    ["eq-liga", "La liga", { q: "liga" }], ["eq-informe", "Informe de equipo", { a: "informeq" }]] },
  { n: "02", t: "Estilos", q: "¿Cómo juega cada equipo?", items: [["es-estilos", "Los seis estilos"], ["es-mapa", "Mapa de estilos", { a: "comparar" }]] },
  { n: "03", t: "Jugadores", q: "¿Cuánto vale cada jugador en su liga?", items: [["nk-liga", "Nivel Kerno de la liga"], ["ficha", "Ficha de jugador"], ["lista", "Lista corta"]] },
  { n: "04", t: "Federación Vasca", q: "Los datos de origen, fase a fase", items: [
    ["fv-jugadores", "Tabla de jugadores", { f: "jugadores" }], ["fv-equipos", "Clasificación por fase", { f: "equipos" }], ["fv-fases", "Fases y divisiones", { f: "fases" }],
    ["fv-calidad", "Calidad de los datos", { f: "calidad" }], ["fv-extraccion", "Extracción", { f: "extraccion" }], ["fv-diccionario", "Diccionario de columnas", { f: "diccionario" }]] },
  { t: "Método", q: "Cómo se calcula y dónde termina lo que sabemos", items: [["como-leer", "Cómo leer los datos"], ["nk-metodo", "Nivel Kerno: método"], ["me-guia", "Guía de conceptos", { q: "aprende" }]] },
];
const LEAD = {
  "eq-evaluacion": "El equipo al completo: Nivel Kerno de su plantilla, balance, rendimiento frente a su liga, entrenador y estilo.",
  "eq-rotacion": "Radiografía de la rotación: Net, suerte, quintetos de referencia, estabilidad y clutch.",
  "eq-quintetos": "Qué cinco funcionan juntos, con su Net ajustado por muestra y su sinergia.",
  "eq-parejas": "Quién suma con quién: minutos juntos y por separado, y sinergia de cada pareja y trío.",
  "eq-conexiones": "La red de pases del equipo y cómo cambia cada jugador el juego de sus compañeros.",
  "eq-impacto": "On/off, RAPM, rol, Nivel Kerno y perfil de tiro de cada jugador.",
  "eq-liga": "Los quintetos, parejas y jugadores con más rendimiento de la liga, y la estructura de cada equipo frente a su rendimiento.",
  "eq-informe": "El documento para la dirección deportiva sobre el estado de un equipo frente a su liga: identidad, rendimiento, entrenador y tiempos muertos, rotación, quintetos y conexiones. Se descarga en PDF.",
  "es-estilos": "Pistons, Isolation, Old-School, Spacing, Circulación y Pintura: qué define cada uno y cómo se reparten los equipos de cada liga vasca.",
  "es-mapa": "El mapa de estilos de todos los equipos y jugadores: compara hasta cuatro y mira en qué se diferencian.",
  "nk-liga": "Todos los jugadores de una liga vasca ordenados por Nivel Kerno, con su rango del 80 %, producción e impacto.",
  ficha: "Nivel Kerno, perfil por percentiles frente a su liga y trayectoria temporada a temporada.",
  lista: "Tus candidatos guardados y la comparativa de hasta tres, lado a lado.",
  "fv-jugadores": "Estadística individual de la Federación por temporada, competición, división, fase y equipo.",
  "fv-equipos": "Clasificación, ratings y cuatro factores por fase y división.", "fv-fases": "Cómo se organizan las fases y las divisiones A1 y A2.",
  "fv-calidad": "Actas, jugada a jugada y controles por temporada y liga.", "fv-extraccion": "Arquitectura por capas, norma de completitud y cómo se lanza la actualización.",
  "fv-diccionario": "Cada columna de la salida unificada con su descripción.",
  "como-leer": "Escala 0–100, percentiles, rangos y lo que la herramienta no estima, dicho claro.",
  "nk-metodo": "De qué métricas nace el Nivel Kerno vasco, cómo se combinan y cómo se lee su rango.",
  "me-guia": "Cada concepto de Equipos con su fórmula, cómo se lee y sus límites.",
};
const APLICA = { inicio: "cte", ficha: "t", lista: "", "nk-liga": "ct", "es-estilos": "t", "es-mapa": "ct", "como-leer": "", "nk-metodo": "", "me-guia": "" };
const ITEM = {};
NAV.forEach((s) => s.items.forEach(([id, n, det]) => { ITEM[id] = { id, n, det: det || null, sec: s }; }));
function marcarAplica() {
  const a = APLICA[S.route] ?? (ITEM[S.route] && ITEM[S.route].det && ITEM[S.route].det.f ? "" : "ct");
  [["fClub", "c"], ["fTemp", "t"], ["fEnt", "e"]].forEach(([id, k]) => { const el = $(id); if (!el) return; const on = a.includes(k); el.classList.toggle("off", !on); el.title = on ? "" : "No se aplica a esta vista: se guarda para las demás"; });
}
function pintarRail() {
  const sec = (s) => `<div class="sec"><div class="sec-h"><span class="n">${s.n || "··"}</span><span class="t">${esc(s.t)}</span>${s.q ? `<span class="q">${esc(s.q)}</span>` : ""}</div>
    ${s.items.map(([id, n]) => `<button class="nav" type="button" data-go="${id}">${esc(n)}</button>`).join("")}</div>`;
  $("rail").innerHTML = `<div class="rail-sitios"><span class="label">Kerno Basque Analytics</span><button class="sitio aqui" type="button" data-go="inicio" aria-current="true"><span class="ini" aria-hidden="true">E</span><b>Equipos</b><span class="est">Estás aquí</span><small>Diagnóstico, estilos, Nivel Kerno y datos de la Federación Vasca</small><span class="cnt">${NAV.reduce((a, s) => a + s.items.length, 0)} herramientas · 4 ligas</span></button></div>`
    + NAV.map(sec).join("")
    + `<div class="rail-foot"><p class="label">Fuente</p><p>Datos públicos · basketbasko.com · Federación Vasca de Baloncesto. Jugada a jugada desde 2022-23.</p><p class="label" style="margin-top:8px">Discreción por diseño</p><p>La lista corta y los ajustes se guardan solo en este navegador.</p></div>`;
}
function marcarNav() { document.querySelectorAll("#rail .nav").forEach((b) => { if (b.dataset.go === S.route) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current"); }); }

const S = { route: "inicio", tk: 0, fk: null };
const HIST = []; let atrasando = false;
function apuntar(id) {
  const f = id === "ficha" ? LS.get("kb.ficha") : null, u = HIST[HIST.length - 1];
  if (atrasando) atrasando = false; else if (u && u.id === id) { if (f) u.f = f; } else { HIST.push({ id, f }); if (HIST.length > 80) HIST.shift(); }
  const b = $("backBtn"), p = HIST[HIST.length - 2]; b.disabled = !p; b.title = p ? "Volver a " + ((ITEM[p.id] || ITEM.inicio).n) : "No hay pantalla anterior";
}
function atras() { if (HIST.length < 2) return; HIST.pop(); const p = HIST[HIST.length - 1]; if (p.f) LS.set("kb.ficha", p.f); atrasando = true; navegar(p.id); }
function navegar(id) { if (!ITEM[id]) id = "inicio"; if (location.hash.slice(1) === id) ir(id); else location.hash = id; }
function ir(id) {
  const it = ITEM[id] || ITEM.inicio; S.route = it.id; S.tk++; apuntar(it.id);
  marcarNav(); marcarAplica(); cerrarRail();
  const sec = it.sec, vh = $("vhead");
  document.title = it.id === "inicio" ? "Kerno Basque Analytics · Equipos" : `${it.n} · Kerno Basque Analytics`;
  vh.hidden = it.id === "inicio";
  const a = APLICA[it.id] ?? (it.det && it.det.f ? "" : "ct"), club = clubActual(), p = [];
  if (a.includes("c") && club) p.push(esc(club.nombre)); if (a.includes("t")) p.push(esc(CTX.temp || "")); if (a.includes("c")) p.push(esc(ligaN(CTX.liga)));
  vh.innerHTML = `<div><div class="eyebrow"><span>${sec.n ? `${sec.n} · ` : ""}${esc(sec.t.toUpperCase())}</span>${it.det ? `<span class="tag">Herramienta de detalle</span>` : ""}</div><h1>${esc(it.n)}</h1>${LEAD[it.id] ? `<p>${esc(LEAD[it.id])}</p>` : ""}</div>
    ${p.length ? `<div class="aplica"><span class="label">Aplicado</span><span>${p.join(" · ")}</span></div>` : `<div class="aplica"><span class="label">${it.det && it.det.f ? "Filtros propios" : "Sin filtros"}</span><span>${it.det && it.det.f ? "Temporada, competición, liga y equipo, en la vista" : "Contenido general"}</span></div>`}`;
  if (it.det) { $("paneNative").hidden = true; $("paneLegacy").hidden = false; abrirDetalle(it.det); }
  else { $("paneLegacy").hidden = true; $("paneNative").hidden = false; $("paneNative").scrollTop = 0; (VISTAS[it.id] || VISTAS.inicio)(S.tk); }
}

// ---------------------------------------------------------------------------------------------- herramientas de detalle
const FR = { q: null, a: null, f: null };
function marco(k, src) {
  let fr = FR[k];
  if (!fr) { fr = document.createElement("iframe"); fr.className = "legacy"; fr.title = { q: "Equipos y quintetos", a: "Atlas de estilos e informe de equipo", f: "Datos de la Federación Vasca" }[k];
    fr.addEventListener("load", () => { fr.dataset.listo = "1"; if (k !== "f") publicarCtx(); }); $("paneLegacy").appendChild(fr); FR[k] = fr; fr.src = src; return { fr, nuevo: true }; }
  return { fr, nuevo: false };
}
function abrirDetalle(det) {
  Object.entries(FR).forEach(([k, fr]) => { if (fr) fr.hidden = !(det[k] != null); });
  if (det.q) {
    const q = { tab: det.q, t: CTX.temp, l: CTX.liga, e: CTX.id, ...(S.q || {}) }; S.q = null;
    const h = new URLSearchParams(Object.entries(q).filter(([, v]) => v != null && v !== "")).toString();
    const { fr, nuevo } = marco("q", "quintetos/index.html#" + h);
    if (!nuevo) { fr.hidden = false; try { fr.contentWindow.postMessage({ irQuintetos: q }, "*"); } catch (e) { fr.src = "quintetos/index.html#" + h; } }
  } else if (det.a) {
    publicarCtx();
    const { fr, nuevo } = marco("a", "atlas/index.html#" + det.a);
    if (!nuevo) { fr.hidden = false; try { fr.contentWindow.postMessage({ irA: det.a }, "*"); fr.contentWindow.postMessage({ cernoCtx: JSON.parse(LS.get("cerno.ctx") || "null") }, "*"); } catch (e) { /* */ } }
  } else if (det.f) {
    const { fr, nuevo } = marco("f", "federacion.html#" + det.f);
    if (!nuevo) { fr.hidden = false; try { fr.contentWindow.location.hash = det.f; } catch (e) { fr.src = "federacion.html#" + det.f; } }
  }
}
// relevo de capacidades para los marcos: descargas del informe en PDF y nota del analista redactada por Claude
const desdeMarco = (e) => Object.values(FR).some((fr) => fr && e.source === fr.contentWindow);
window.addEventListener("message", async (e) => {
  if (!desdeMarco(e)) return;
  const d = e.data || {};
  if (d.ebateExport) {
    const x = d.ebateExport, resp = (r) => { try { e.source.postMessage({ ebateExportRes: { id: x.id, ...r } }, "*"); } catch (er) { /* */ } };
    try {
      const datos = typeof x.datos === "string" ? x.datos : new Blob([x.datos], { type: x.tipo || "application/octet-stream" });
      if (x.accion === "abrir") { const url = URL.createObjectURL(typeof datos === "string" ? new Blob([datos], { type: x.tipo }) : datos); const w = window.open(url, "_blank"); try { if (w) w.opener = null; } catch (er) { /* */ } setTimeout(() => URL.revokeObjectURL(url), 300000); resp(w === null ? { error: "ventana_bloqueada" } : { ok: true }); return; }
      const dl = window.claude && window.claude.use ? await window.claude.use("downloads") : null;
      if (!dl) { resp({ error: "unavailable" }); return; }
      await dl.save({ filename: x.nombre, data: datos }); resp({ ok: true });
    } catch (er) { resp({ error: (er && er.code) || String((er && er.message) || er) }); }
  }
  if (d.cernoSample) {
    const x = d.cernoSample, resp = (r) => { try { e.source.postMessage({ cernoSampleRes: { id: x.id, ...r } }, "*"); } catch (er) { /* */ } };
    let s = null; try { s = window.claude && window.claude.use ? await window.claude.use("sample") : null; } catch (er) { s = null; }
    if (!s) { resp({ error: "unavailable" }); return; }
    try { const r = await s(x.prompt, { modelTier: "default" }); resp({ text: r && r.text, truncated: r && r.truncated }); }
    catch (er) { resp({ error: (er && er.code) || String((er && er.message) || er), text: er && er.text }); }
  }
  if (d.irClaves) navegar("es-estilos");
});

// ---------------------------------------------------------------------------------------------- utilidades de vista
const V = () => $("view");
const vigente = (tk) => tk === S.tk;
const cargando = (txt) => `<div class="loading"><div class="estela" aria-hidden="true"></div><span class="label">${esc(txt || "Cargando datos")}</span></div>`;
const fallo = (e) => `<div class="callout"><span class="label">No se pudieron cargar los datos</span><p>${esc(e && e.message ? e.message : e)}. Recarga la página; si persiste, el archivo no está publicado junto a la herramienta.</p></div>`;
const PASO = { inicio: 0, "eq-": 1, "es-": 2, "nk-": 3, ficha: 3, lista: 3, "fv-": 4 };
const ticks = () => { const k = Object.keys(PASO).find((x) => S.route.startsWith(x)); const on = k ? PASO[k] : 0; return `<span class="k-ticks" aria-hidden="true">${[0, 1, 2, 3, 4, 5, 6, 7].map((i) => `<i${i === on ? ' class="on"' : ""}></i>`).join("")}</span>`; };
const pie = (txt) => `<p class="src">${ticks()}<span>Datos públicos · basketbasko.com (Federación Vasca de Baloncesto) · actas y jugada a jugada · ${esc(txt || "")} · Kerno Basque Analytics</span></p>`;
function toast(t) { const el = $("toast"); el.textContent = t; el.hidden = false; clearTimeout(toast.k); toast.k = setTimeout(() => { el.hidden = true; }, 2600); }
function abrirFicha(r) { LS.set("kb.ficha", r.k); navegar("ficha"); }
const filaJug = (r) => `${esc(r.equipo)} · ${esc(LIGA_C[r.liga] || r.liga)}${r.pos3 ? ` · ${POS[r.pos3]}` : ""}`;
const LISTA = { get: () => LS.json("kb.lista", []), set: (a) => LS.set("kb.lista", JSON.stringify(a)) };
const enLista = (k) => LISTA.get().some((x) => x.k === k);
function alternarLista(r) {
  const a = LISTA.get(), i = a.findIndex((x) => x.k === r.k);
  if (i >= 0) { a.splice(i, 1); toast(`${r.nombre} sale de la lista corta`); } else { a.push({ k: r.k, nombre: r.nombre, equipo: r.equipo, liga: r.liga, temp: r.T.temp, cmp: a.filter((x) => x.cmp).length < 3 }); toast(`${r.nombre} entra en la lista corta`); }
  LISTA.set(a);
}
const estSpan = (lab, i, p) => (lab ? `<span title="${esc((ESTILOS[i] || {}).jugador || "")}"><i class="estsw" style="background:${EST_COL[i] || "var(--faint)"}"></i>${esc(lab)}${ok(p) ? ` <span class="rng">${Math.round(100 * p)} %</span>` : ""}</span>` : `<span class="rng">s/d</span>`);

// ---------------------------------------------------------------------------------------------- VISTAS
const VISTAS = {};

// ---- Lectura: tu equipo hoy
VISTAS.inicio = async (tk) => {
  V().innerHTML = cargando("Leyendo tu equipo");
  let T; try { [T] = await Promise.all([temporada(CTX.temp), equipos(), estilosClubes()]); pintarEnt(); } catch (e) { if (vigente(tk)) V().innerHTML = fallo(e); return; }
  if (!vigente(tk)) return;
  const club = clubActual(), nombre = club ? club.nombre : "Tu equipo", info = clubInfo(CTX.temp, CTX.liga, CTX.id) || {};
  const lg = eqFilas(CTX.temp, CTX.liga), mine = lg.find((r) => r.id === CTX.id), N = lg.length;
  const rank = (c, dir) => 1 + lg.filter((r) => ok(r[c]) && (dir > 0 ? r[c] > mine[c] : r[c] < mine[c])).length;
  const media = (c) => { const v = lg.map((r) => r[c]).filter(ok); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };
  const sd = (c) => { const m = media(c), v = lg.map((r) => r[c]).filter(ok); return Math.sqrt(v.reduce((s, x) => s + (x - m) ** 2, 0) / Math.max(1, v.length - 1)); };
  const tempTxt = `${ligaN(CTX.liga)} ${CTX.temp}${enCurso(CTX.temp) ? " (en curso)" : ""}`;
  let cab = "", kpis = "", ff = "", est = "";
  if (mine) {
    const rN = rank("net", 1), rO = rank("ortg", 1), rD = rank("drtg", -1), rP = rank("ritmo", 1);
    const prob = rD > rO + 2 ? "Falla la defensa." : rO > rD + 2 ? "Falla el ataque." : "Ataque y defensa, parejos.";
    const muestra = mine.gp < 10 ? ` ${mine.gp} partidos: muestra corta.` : "";
    const nP = nivelPlantilla(CTX.temp, CTX.liga, mine.L), rPl = ok(mine.L) ? 1 + lg.filter((r) => ok(r.L) && r.L > mine.L).length : null;
    cab = `<div class="block hero"><div class="eyebrow"><span>LECTURA · ${esc(tempTxt.toUpperCase())}</span>${info.division && info.division !== "única" ? `<span>DIVISIÓN ${esc(info.division)}</span>` : ""}<span class="tag">Lectura</span></div>
      <h2 class="read-h">${esc(nombre)}: <span class="hl">${ord(rN)} de ${N}</span> en diferencial, ${sgn(mine.net)} por 100 posesiones.</h2>
      <p class="read-lead">Ataque ${ord(rO)}, defensa ${ord(rD)}, balance ${mine.w}–${mine.l}. ${prob}${muestra}${ok(nP) ? ` Plantilla: Nivel Kerno ${Math.round(nP)} (${ord(rPl)} de ${N}).` : ""}</p></div>`;
    kpis = `<div class="block"><div class="block-h"><div><h3 class="h2">El equipo en cifras</h3><p class="sub">Toda la temporada · por 100 posesiones · puesto en ${esc(ligaN(CTX.liga))}</p></div><span class="tag dato">Dato</span></div>
      <div class="kpis">
        <div class="kpi key"><span class="label">Diferencial (Net)</span><span class="v ${mine.net >= 0 ? "pos" : "neg"}">${sgn(mine.net)}</span><span class="r">${ord(rN)} de ${N}</span></div>
        <div class="kpi"><span class="label">Balance</span><span class="v">${mine.w}–${mine.l}</span><span class="r">${mine.gp} partidos</span></div>
        <div class="kpi"><span class="label">Rating ofensivo</span><span class="v">${fmt(mine.ortg)}</span><span class="r">${ord(rO)} · media ${fmt(media("ortg"))}</span></div>
        <div class="kpi"><span class="label">Rating defensivo</span><span class="v">${fmt(mine.drtg)}</span><span class="r">${ord(rD)} · media ${fmt(media("drtg"))}</span></div>
        <div class="kpi key"><span class="label" title="Media del Nivel Kerno de sus jugadores (100+ min), ponderada por minutos, frente al club medio de su liga (= 50)">Nivel Kerno de la plantilla</span><span class="v ${ok(nP) ? (nP >= 50 ? "pos" : "neg") : ""}">${ok(nP) ? Math.round(nP) : "—"}</span><span class="r">${rPl ? `${ord(rPl)} de ${N} · 50 = club medio` : "sin dato"}</span></div>
        <div class="kpi"><span class="label">Ritmo</span><span class="v">${fmt(mine.ritmo)}</span><span class="r">${ord(rP)} · posesiones por 40′</span></div>
      </div></div>`;
    const fila = (c, n, s) => { if (!ok(mine[c])) return `<tr><td>${n}</td><td class="n">—</td><td class="n">${fmt(media(c))}</td><td class="n">—</td><td></td></tr>`;
      const z = ((mine[c] - media(c)) / (sd(c) || 1)) * s, wv = Math.min(50, (Math.abs(z) / 2.5) * 50), rr = rank(c, s);
      return `<tr><td>${n}</td><td class="n">${fmt(mine[c])}</td><td class="n">${fmt(media(c))}</td><td class="n">${ord(rr)}</td><td><div class="dv" role="img" aria-label="${z >= 0 ? "Por encima" : "Por debajo"} de la media: ${fmt(Math.abs(z), 1)} desviaciones"><i class="${z >= 0 ? "up" : "dn"}" style="${z >= 0 ? `left:50%` : `left:${(50 - wv).toFixed(1)}%`};width:${wv.toFixed(1)}%"></i></div></td></tr>`; };
    const tabla = (t, rows) => `<div class="block"><h4 class="h3">${t}</h4><div class="tw"><table><thead><tr><th>Factor</th><th class="n">Equipo</th><th class="n">Liga</th><th class="n">Puesto</th><th>Frente a la media</th></tr></thead><tbody>${rows}</tbody></table></div></div>`;
    ff = `<div class="block"><div class="block-h"><div><h3 class="h2">Dónde se gana y dónde se pierde</h3><p class="sub">Cuatro factores · desviaciones frente a la media de la liga · azul a favor, arcilla en contra</p></div><span class="tag dato">Dato</span></div>
      <div class="split">${tabla("En ataque", fila("efg", "Tiro (eFG%)", 1) + fila("tov", "Pérdidas (TOV%)", -1) + fila("orb", "Rebote ofensivo", 1) + fila("ftr", "Tiros libres (FTr)", 1))}
      ${tabla("En defensa", fila("oefg", "Tiro del rival (eFG%)", -1) + fila("otov", "Pérdidas forzadas", 1) + fila("drb", "Rebote defensivo", 1) + fila("oftr", "Tiros libres del rival", -1))}</div></div>`;
    const ec = estiloClub(CTX.temp, CTX.liga, CTX.id);
    if (ec) { const u = ec.u, d = ESTILOS[u[0]] || {};
      est = `<div class="block"><div class="block-h"><div><h3 class="h2">Cómo juega</h3><p class="sub">Estilo de juego · doce rasgos medidos frente a ${esc(ligaN(CTX.liga))} · claridad ${Math.round(100 * u[1])} %</p></div><span class="tag">Lectura</span></div>
        <p class="note" style="color:var(--text-2);font-size:15px"><b>${esc(u[2])}</b>. ${esc(d.equipo || d.definicion || "")}</p>
        ${Array.isArray(ec.pr) ? `<div class="reparto" role="img" aria-label="Reparto entre los seis estilos">${ec.pr.map((p, k) => (p >= 0.01 ? `<i style="width:${(100 * p).toFixed(1)}%;background:${EST_COL[k]}" title="${esc((ESTILOS[k] || {}).nombre || "")}: ${Math.round(100 * p)} %"></i>` : "")).join("")}</div>
        <div class="legend">${ESTILOS.map((e, k) => `<span><i style="background:${EST_COL[k]}"></i>${esc(e.nombre)} ${ec.pr[k] >= 0.01 ? Math.round(100 * ec.pr[k]) + " %" : ""}</span>`).join("")}</div>` : ""}
        <p class="note">Informativo: el estilo describe cómo juega el equipo, no cuánto vale. Detalle en «Los seis estilos» y «Mapa de estilos».</p></div>`; }
  } else {
    cab = `<div class="block hero"><div class="eyebrow"><span>LECTURA · ${esc(tempTxt.toUpperCase())}</span></div><h2 class="read-h">${esc(nombre)}</h2>
      <p class="read-lead">Sin datos de equipo en ${esc(tempTxt)}. Elige otro equipo o temporada arriba.</p></div>`;
  }
  // la plantilla, leída en su liga: Nivel Kerno, producción e impacto
  const ro = T.rows.filter((r) => r.liga === CTX.liga && r.team_id === CTX.id && (r.min || 0) >= 30).sort((a, b) => b.min - a.min);
  let plant = "";
  if (ro.length) {
    const con = ro.filter((r) => ok(r.nk) && r.min >= 100), arriba = con.filter((r) => r.nk_lo > 50).length, abajo = con.filter((r) => r.nk_hi < 50).length;
    const mejor = con.slice().sort((a, b) => b.nk - a.nk)[0], imp = con.filter((r) => ok(r.imp)).sort((a, b) => b.imp - a.imp)[0];
    const lect = `${arriba ? `${arriba} ${arriba === 1 ? "jugador está" : "jugadores están"} con claridad por encima del jugador medio de su liga (todo su rango de Nivel Kerno por encima de 50)` : "Nadie está todavía con claridad por encima del jugador medio de su liga"}, ${abajo ? `${abajo} por debajo` : "nadie claramente por debajo"} y ${con.length - arriba - abajo} en la zona media.${mejor ? ` El Nivel Kerno más alto es el de ${mejor.nombre} (${Math.round(mejor.nk)}).` : ""}${imp && imp !== mejor ? ` El que más mueve el marcador con él en pista es ${imp.nombre} (Impacto ${Math.round(imp.imp)}).` : ""}`;
    plant = `<div class="block"><div class="block-h"><div><h3 class="h2">La plantilla, leída en su liga</h3><p class="sub">Nivel Kerno, producción e impacto · 0–100, 50 = jugador medio de ${esc(ligaN(CTX.liga))} ${esc(CTX.temp)} · rango del 80 %</p></div><span class="tag">Lectura</span></div>
      <p class="note" style="color:var(--text-2);font-size:15px">${esc(lect)}</p>
      <div class="tw"><table class="v4t"><thead><tr><th>Jugador</th><th class="n">Min</th><th class="n">Min/p</th><th class="n" title="Producción e impacto frente a su liga, 0–100">Nivel Kerno</th><th class="bar">0–100 · rango del 80 %</th><th class="n" title="PER, Win Shares, Game Score y PIE por minuto frente a su liga">Producción</th><th class="n" title="RAPM y on/off ajustado frente a su liga">Impacto</th><th class="n" title="RAPM del jugada a jugada, pts/100">RAPM</th><th>Estilo</th></tr></thead><tbody>
      ${ro.map((r) => `<tr class="go" data-k="${esc(r.k)}" tabindex="0"><td><div class="who"><b>${esc(r.nombre)}</b><span>${POS[r.pos3] || "s/d"} · ${r.gp} PJ</span></div></td>
        <td class="n">${Math.round(r.min)}</td><td class="n">${fmt(r.min_pg, 1)}</td><td class="n"><b>${ok(r.nk) ? Math.round(r.nk) : "—"}</b> ${ok(r.nk_lo) ? `<span class="rng">[${Math.round(r.nk_lo)}–${Math.round(r.nk_hi)}]</span>` : ""}</td><td>${nkbar(r.nk, r.nk_lo, r.nk_hi)}</td>
        <td class="n">${ok(r.prod) ? Math.round(r.prod) : "—"}</td><td class="n">${ok(r.imp) ? Math.round(r.imp) : "—"}</td><td class="n">${ok(r.rapm) ? sgn(r.rapm, 1) : "—"}</td><td>${estSpan(r.eu, r.eu_i)}</td></tr>`).join("")}
      </tbody></table></div><p class="note">Jugadores con 30 minutos o más. Pulsa una fila para abrir su ficha. Posición estimada con su perfil estadístico (la Federación no la publica). El rango se estrecha con los minutos: por debajo de 300 es ancho a propósito.</p></div>`;
  }
  const acts = `<div class="block"><div class="block-h"><h3 class="h2">Qué decisión tienes delante</h3></div><div class="acts">
    <button class="act" type="button" data-go="eq-rotacion"><span class="label">01 · Diagnóstico</span><b>Revisar la rotación</b><span>Net por tramos, quintetos de referencia, estabilidad y clutch.</span></button>
    <button class="act" type="button" data-go="eq-informe"><span class="label">01 · Informe</span><b>Llevar el informe a la dirección</b><span>Catorce páginas en PDF: rendimiento, entrenador, tiempos muertos, rotación, quintetos y conexiones.</span></button>
    <button class="act" type="button" data-go="es-estilos"><span class="label">02 · Estilos</span><b>Leer cómo juega la liga</b><span>Los seis estilos y cómo se reparten los equipos de cada liga vasca.</span></button>
    <button class="act" type="button" data-go="nk-liga"><span class="label">03 · Jugadores</span><b>Ordenar la liga por Nivel Kerno</b><span>Todos los jugadores de la liga, con su rango, producción e impacto.</span></button></div></div>`;
  V().innerHTML = cab + kpis + banquilloHTML() + plant + est + ff + acts + pie(tempTxt);
};

// ---- El banquillo (etapas de entrenador, con los ids de equipo estables entre temporadas)
function banquilloHTML() {
  if (!EQ) return "";
  const club = clubActual(), nom = club ? club.nombre : "el equipo", ets = etapasClub(CTX.liga, CTX.id), hoyT = ets.filter((e) => e.temp === CTX.temp), sel = entActual();
  const estiloEt = (e) => { const c = estiloClub(e.temp, CTX.liga, CTX.id), x = c && c.ent && c.ent[e.id]; return x ? `${esc(x[2])} <span class="rng">${Math.round(x[1] * 100)} %</span>` : c ? `${esc(c.u[2])}` : `<span class="rng">s/d</span>`; };
  const fila = (e, conT) => { const n = (e.w || 0) + (e.l || 0), pct = n ? (100 * e.w) / n : null, nP = nivelPlantilla(e.temp, CTX.liga, e.L);
    return `<tr class="${sel && e.id === sel.id ? "sel" : ""}">${conT ? `<td class="num">${e.temp}</td>` : ""}<td><div class="who"><b>${esc(e.n)}</b><span>${fecha(e.de)} – ${fecha(e.a)}</span></div></td>
      <td class="n">${e.pj ?? "—"}</td><td class="n">${n ? `${e.w}–${e.l}` : "—"}</td>
      <td><div class="wl" role="img" aria-label="${pct == null ? "Sin balance" : Math.round(pct) + " % de victorias"}"><i style="width:${pct == null ? 0 : pct.toFixed(1)}%"></i></div></td><td class="n">${pct == null ? "—" : Math.round(pct) + " %"}</td>
      <td class="n">${ok(nP) ? Math.round(nP) : "—"}</td><td>${estiloEt(e)}</td></tr>`; };
  const cab = (conT) => `<thead><tr>${conT ? "<th>Temporada</th>" : ""}<th>Entrenador · etapa</th><th class="n">PJ</th><th class="n">Balance</th><th colspan="2">% victorias</th><th class="n" title="Nivel Kerno de la plantilla de esa temporada (50 = club medio de su liga)">Plantilla</th><th>Estilo</th></tr></thead>`;
  let lect;
  if (hoyT.length) { const ns = hoyT.flatMap((e) => String(e.n).split(" · ")), varios = ns.length > 1;
    lect = `${varios ? `Con licencia de entrenador: ${ns.slice(0, -1).join(", ")} y ${ns[ns.length - 1]}` : `${ns[0]} dirige ${enCurso(CTX.temp) ? "la temporada hasta ahora" : "toda la temporada"}`}. Balance ${hoyT[0].w}–${hoyT[0].l} en ${hoyT[0].pj} partidos. La Federación publica los entrenadores con licencia del equipo, no quién dirige cada partido: con varias licencias, la etapa es de todas.`; }
  else lect = `Sin entrenador con licencia para ${nom} en ${CTX.temp}.`;
  let det = "";
  if (sel) {
    const W = sel.et.reduce((a, e) => a + (e.w || 0), 0), L = sel.et.reduce((a, e) => a + (e.l || 0), 0), ts = [...new Set(sel.et.map((e) => e.temp))];
    det = `<div class="block"><h4 class="h3">${esc(sel.n)} en ${esc(nom)}</h4>
      <p class="note" style="color:var(--text-2);font-size:15px">${sel.et.length} ${sel.et.length === 1 ? "temporada" : "temporadas"} (${ts[0]}${ts.length > 1 ? ` a ${ts[ts.length - 1]}` : ""}): ${W}–${L}, ${Math.round((100 * W) / (W + L || 1))} % de victorias en ${esc(ligaN(CTX.liga))}.</p>
      <div class="tw"><table>${cab(true)}<tbody>${sel.et.map((e) => fila(e, true)).join("")}</tbody></table></div></div>`;
  }
  return `<div class="block"><div class="block-h"><div><h3 class="h2">El banquillo</h3><p class="sub">Entrenadores con licencia · balance, nivel de la plantilla y estilo de cada temporada</p></div><span class="tag dato">Dato</span></div>
    <p class="note" style="color:var(--text-2);font-size:15px">${esc(lect)}</p>
    ${hoyT.length ? `<div class="tw"><table>${cab(false)}<tbody>${hoyT.map((e) => fila(e, false)).join("")}</tbody></table></div>` : ""}
    ${det || (ets.length > hoyT.length ? `<p class="note">Elige un entrenador arriba para ver todas sus temporadas en ${esc(nom)}. En el informe de equipo, su trayectoria en todos los equipos vascos.</p>` : "")}</div>`;
}

// ---- Ficha de jugador
let TRAY = null;
VISTAS.ficha = async (tk) => {
  V().innerHTML = cargando("Preparando la ficha");
  const k = LS.get("kb.ficha"); let t = k ? k.split("|")[0] : CTX.temp; if (!TEMPS.includes(t)) t = CTX.temp;
  try { await Promise.all([temporada(t), temporada(CTX.temp), equipos(), estilosClubes()]); } catch (e) { if (vigente(tk)) V().innerHTML = fallo(e); return; }
  if (!vigente(tk)) return;
  const r = porClave(k);
  if (!r) {
    const ro = SEAS[CTX.temp].rows.filter((x) => x.liga === CTX.liga && x.team_id === CTX.id).sort((a, b) => b.min - a.min).slice(0, 10);
    V().innerHTML = `<div class="block"><h2 class="h2">Elige un jugador</h2><p class="note">Busca en las cuatro ligas vascas de la temporada en contexto o empieza por tu plantilla.</p>
      <div><button class="btn" type="button" data-act="buscar">Buscar jugador</button></div>
      <div class="chips">${ro.map((x) => `<button class="chip" type="button" data-k="${esc(x.k)}"><b>${esc(x.nombre)}</b><span>${filaJug(x)}</span></button>`).join("")}</div></div>`;
    return;
  }
  S.fk = r.k;
  const T = r.T, favs = [];
  GRUPOS.slice(1, 5).forEach(([, , ms]) => ms.forEach((m) => { const e = est(r, m); if (e && e.s !== 0) favs.push(e); }));
  const fuertes = favs.filter((e) => e.p >= 75).sort((a, b) => b.p - a.p).slice(0, 3), flojos = favs.filter((e) => e.p <= 25).sort((a, b) => a.p - b.p).slice(0, 2);
  const lista = (a) => a.map((e) => `${(M[e.m].c || M[e.m].n.toLowerCase())} (percentil ${Math.round(e.p)})`).join(", ");
  const readH = ok(r.nk) ? `Nivel Kerno ${Math.round(r.nk)} [${Math.round(r.nk_lo)}–${Math.round(r.nk_hi)}] en ${ligaN(r.liga)} ${T.temp}: ${nivelTxt(r.nk)} frente al jugador medio de su liga. Producción ${Math.round(r.prod)}${ok(r.imp) ? `, impacto ${Math.round(r.imp)}` : ""}.` : "Sin Nivel Kerno: muy pocos minutos.";
  const readL = (fuertes.length ? `Destaca en ${lista(fuertes)}.` : "No destaca con claridad en ninguna faceta medida.") + " " + (flojos.length ? `Queda por debajo de la media en ${lista(flojos)}.` : "Ninguna faceta claramente por debajo de la media.");
  const lst = enLista(r.k), otras = T.rows.filter((x) => x !== r && x.player_id === r.player_id);
  const tray = TRAY && TRAY.pid === r.player_id ? TRAY : null;
  const kp = ok(r.nk) ? `<div class="block"><div class="block-h"><div><h3 class="h2">Nivel Kerno en ${esc(ligaN(r.liga))}</h3><p class="sub">${esc(T.temp)} · 0–100, 50 = jugador medio de su liga (ponderado por minutos) · rango del 80 %</p></div><span class="tag">Lectura</span></div>
      <div class="kpis">
        <div class="kpi key"><span class="label" title="0,6 · producción + 0,4 · impacto, frente a su liga">Nivel Kerno</span><span class="v">${Math.round(r.nk)}</span><span class="r">[${Math.round(r.nk_lo)}–${Math.round(r.nk_hi)}] · ${nivelTxt(r.nk)} · confianza ${confTxt(r)}</span></div>
        <div class="kpi"><span class="label" title="PER, Win Shares por 40, Game Score por 40 y PIE frente a su liga">Producción</span><span class="v">${Math.round(r.prod)}</span><span class="r">lo que produce por minuto</span></div>
        <div class="kpi"><span class="label" title="RAPM y on/off ajustado frente a su liga">Impacto</span><span class="v">${ok(r.imp) ? Math.round(r.imp) : "—"}</span><span class="r">${ok(r.imp_lo) ? `[${Math.round(r.imp_lo)}–${Math.round(r.imp_hi)}] · marcador con él en pista` : "sin jugada a jugada"}</span></div>
        <div class="kpi"><span class="label">RAPM</span><span class="v ${r.rapm >= 0 ? "pos" : "neg"}">${ok(r.rapm) ? sgn(r.rapm, 1) : "—"}</span><span class="r">pts/100 sobre el jugador medio</span></div>
      </div><p class="note">El Nivel Kerno se mide dentro de su liga y temporada: un 70 en Cadete no es un 70 en Primera Nacional (no hay puente de normalización entre ligas vascas). Detalle en «Nivel Kerno: método».</p></div>` : "";
  V().innerHTML = `
    <div class="block hero"><div class="eyebrow"><span>FICHA · ${esc(ligaN(r.liga).toUpperCase())} · ${esc(T.temp)}</span>${otras.length ? `<span>También en: ${otras.map((x) => `<button class="btn quiet" style="min-height:26px;padding:2px 8px" type="button" data-k="${esc(x.k)}">${esc(x.equipo)}</button>`).join(" ")}</span>` : ""}</div>
      <h2 class="read-h${bombOK(r.nombre) ? " disp" : ""}" style="max-width:none">${esc(r.nombre)}</h2>
      <div class="idt"><span>Equipo <b>${esc(r.equipo)}</b></span><span>Posición <b>${POS[r.pos3] || "s/d"}</b> <span class="rng">estimada</span></span>${r.division && r.division !== "única" ? `<span>División <b>${esc(r.division)}</b></span>` : ""}<span>Estilo <b>${esc(r.eu || "s/d")}</b></span><span>Muestra <b class="num">${Math.round(r.min)}′ · ${r.gp} PJ</b></span><span>Por partido <b class="num">${fmt(r.pts_pg, 1)} pts · ${fmt(r.reb_pg, 1)} reb</b></span></div>
      <p class="read-lead strong">${esc(readH)}</p><p class="read-lead" style="font-size:18px;line-height:26px">${esc(readL)}</p>
      <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center">
        <button class="btn" type="button" data-act="lista">${lst ? "Quitar de la lista corta" : "Añadir a la lista corta"}</button>
        <button class="btn sec" type="button" data-act="impacto">Impacto en pista</button>
        <button class="btn quiet" type="button" data-act="informeq">Informe de su equipo</button></div></div>
    <div class="q4" aria-label="Las cuatro preguntas">
      <div><span class="label">Nivel</span><span class="v">${ok(r.nk) ? `${Math.round(r.nk)} · ${nivelTxt(r.nk)}` : "s/d"}</span><p>Frente al jugador medio de ${esc(ligaN(r.liga))} en ${esc(T.temp)}.</p></div>
      <div><span class="label">Impacto</span><span class="v">${ok(r.imp) ? Math.round(r.imp) : "s/d"}</span><p>Lo que cambia el marcador de su equipo con él en pista (RAPM y on/off ajustado).</p></div>
      <div id="q4tray"><span class="label">Trayectoria</span>${tray ? trayResumen(tray) : `<button class="btn quiet" type="button" data-act="tray">Cargar trayectoria</button><p>Todas sus temporadas con jugada a jugada (2022-23 en adelante).</p>`}</div>
      <div><span class="label">Riesgo</span><span class="v">Confianza ${confTxt(r)}</span><p>${Math.round(r.min)}′ de muestra${r.min < 300 ? ": por debajo de 300 minutos el rango es ancho a propósito" : ""}.</p></div>
    </div>
    ${kp}
    <div class="block"><div class="block-h"><div><h3 class="h2">Perfil por percentiles</h3><p class="sub">Frente a los jugadores de ${esc(ligaN(r.liga))} ${esc(T.temp)} con 100+ minutos · marcas en 25 / 50 / 75 · menos es mejor, ya invertido</p></div><span class="tag">Lectura</span></div>
      <div class="prof">${GRUPOS.map(([n, d, ms]) => `<div class="g"><span>${n}</span><small>${esc(d)}</small></div>` + ms.map((m) => { const e = est(r, m); return `<div class="m">${M[m].n}${e && e.s === -1 ? "<small>menos es mejor; la barra ya está invertida</small>" : ""}</div>${pbar(e, true)}<div class="val">${valHTML(e, true)}</div>`; }).join("")).join("")}
        <div></div><div class="axis"><span>0</span><span>25</span><span>50</span><span>75</span><span>100</span></div><div></div></div></div>
    <div class="block" id="trayBlock">${tray ? trayHTML(tray) : ""}</div>
    <div class="callout"><span class="label">Qué cambiaría la lectura</span><p>La lectura descansa en ${Math.round(r.min)} minutos (${r.gp} partidos)${enCurso(T.temp) ? " de una temporada en curso" : ""}. Más minutos con el mismo rol estrechan el rango; un rol distinto (más uso, otra posición) o un salto de categoría lo moverían. Asistencias y tapones solo cuentan donde la mesa los registra (asistencias: 2026-27).</p></div>
    ${pie(`${ligaN(r.liga)} ${T.temp}`)}`;
};
async function cargarTrayectoria(r) {
  const box = $("q4tray"); if (box) box.innerHTML = `<span class="label">Trayectoria</span>${cargando("Leyendo temporadas")}`;
  const filas = [];
  for (const t of TEMPS.slice().sort()) { let T; try { T = await temporada(t); } catch (e) { continue; } const xs = T.rows.filter((x) => x.player_id === r.player_id); if (xs.length) filas.push(...xs.sort((a, b) => b.min - a.min)); }
  TRAY = { pid: r.player_id, filas };
  if (S.route === "ficha" && S.fk === r.k) { $("q4tray").innerHTML = `<span class="label">Trayectoria</span>${trayResumen(TRAY)}`; $("trayBlock").innerHTML = trayHTML(TRAY); }
}
function trayResumen(tr) {
  const xs = tr.filas.filter((x) => ok(x.nk) && x.min >= 100);
  if (xs.length < 2) return `<span class="v">${tr.filas.length} ${tr.filas.length === 1 ? "temporada" : "registros"}</span><p>Sin dos temporadas con 100+ minutos para leer una tendencia.</p>`;
  const a = xs[xs.length - 2], b = xs[xs.length - 1], solapa = !(a.nk_hi < b.nk_lo || b.nk_hi < a.nk_lo), mismaL = a.liga === b.liga;
  return `<span class="v">${!mismaL ? "Cambio de liga" : solapa ? "Sin cambio claro" : b.nk > a.nk ? "Al alza" : "A la baja"}</span><p>Nivel Kerno ${Math.round(a.nk)} en ${a.T.temp} (${LIGA_C[a.liga]}) y ${Math.round(b.nk)} en ${b.T.temp} (${LIGA_C[b.liga]})${!mismaL ? ": cada uno frente a su liga." : solapa ? ": los rangos se solapan." : "."}</p>`;
}
function trayHTML(tr) {
  const pts = tr.filas.filter((x) => ok(x.nk)); if (!pts.length) return "";
  const W = 720, H = 240, L = 46, R = 40, Tp = 18, B = 34, n = pts.length, lo = 0, hi = 100;
  const xs = (i) => L + (n === 1 ? (W - L - R) / 2 : (i * (W - L - R)) / (n - 1)), ys = (v) => Tp + ((hi - v) * (H - Tp - B)) / (hi - lo);
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Nivel Kerno por temporada con su rango del 80 %">`;
  for (let v = lo; v <= hi; v += 25) svg += `<line class="${v === 50 ? "zl" : "gl"}" x1="${L}" x2="${W - R}" y1="${ys(v)}" y2="${ys(v)}"/><text class="ax" x="${L - 8}" y="${ys(v) + 4}" text-anchor="end">${v}</text>`;
  pts.forEach((p, i) => { svg += `<rect class="bd" x="${xs(i) - 9}" y="${ys(p.nk_hi)}" width="18" height="${Math.max(1, ys(p.nk_lo) - ys(p.nk_hi))}"/><text class="ax" x="${xs(i)}" y="${H - 12}" text-anchor="middle">${p.T.temp} · ${LIGA_C[p.liga]}</text>`; });
  svg += `<polyline class="ln" points="${pts.map((p, i) => `${xs(i)},${ys(p.nk)}`).join(" ")}"/>`;
  pts.forEach((p, i) => { const last = i === n - 1 && n > 1; svg += `<circle class="pt${i === n - 1 ? " rd" : ""}" cx="${xs(i)}" cy="${ys(p.nk)}" r="4"/><text class="lb" x="${xs(i) + (last ? -14 : 14)}" y="${ys(p.nk) - 8}" text-anchor="${last ? "end" : "start"}">${Math.round(p.nk)}</text>`; });
  svg += `</svg>`;
  return `<div class="block-h"><div><h3 class="h2">Trayectoria del Nivel Kerno</h3><p class="sub">Cada temporada frente a su liga (50 = jugador medio) · punto y rango del 80 %</p></div><span class="tag">Lectura</span></div>
    <div class="chart">${svg}</div>
    <div class="tw"><table><thead><tr><th>Temporada</th><th>Equipo</th><th class="n">Min</th><th class="n">Nivel Kerno</th><th class="n">Producción</th><th class="n">Impacto</th><th class="n">Pts/p</th><th>Estilo</th></tr></thead><tbody>
    ${tr.filas.map((x) => `<tr class="go" data-k="${esc(x.k)}" tabindex="0"><td class="num">${x.T.temp}${enCurso(x.T.temp) ? " · en curso" : ""}</td><td>${esc(x.equipo)} <span class="rng">${esc(LIGA_C[x.liga])}</span></td><td class="n">${Math.round(x.min)}</td><td class="n"><b>${ok(x.nk) ? Math.round(x.nk) : "—"}</b> ${ok(x.nk_lo) ? `<span class="rng">[${Math.round(x.nk_lo)}–${Math.round(x.nk_hi)}]</span>` : ""}</td><td class="n">${ok(x.prod) ? Math.round(x.prod) : "—"}</td><td class="n">${ok(x.imp) ? Math.round(x.imp) : "—"}</td><td class="n">${fmt(x.pts_pg, 1)}</td><td>${estSpan(x.eu, x.eu_i)}</td></tr>`).join("")}
    </tbody></table></div><p class="note">Un jugador puede jugar en dos categorías la misma temporada (por ejemplo, Junior y Primera Nacional): cada fila se lee frente a su liga.</p>`;
}

// ---- Nivel Kerno de la liga
const NKF = Object.assign({ liga: "", pos: "", min: 100, q: "", ver: 60 }, LS.json("kb.nkf", {}));
VISTAS["nk-liga"] = async (tk) => {
  V().innerHTML = cargando("Ordenando la liga");
  let T; try { [T] = await Promise.all([temporada(CTX.temp), equipos(), estilosClubes()]); } catch (e) { if (vigente(tk)) V().innerHTML = fallo(e); return; }
  if (!vigente(tk)) return;
  const liga = NKF.liga || CTX.liga, q = norm(NKF.q).trim();
  const rows = T.rows.filter((r) => r.liga === liga && ok(r.nk) && (r.min || 0) >= +NKF.min && (!NKF.pos || r.pos3 === NKF.pos) && (!q || norm(r.nombre + " " + r.equipo).includes(q))).sort((a, b) => b.nk - a.nk);
  const nT = T.rows.filter((r) => r.liga === liga && ok(r.nk)).length;
  V().innerHTML = `<div class="block"><div class="filtros">
      <label><span class="label">Liga</span><select id="nkLiga">${LIGAS.filter((l) => T.rows.some((r) => r.liga === l)).map((l) => `<option value="${l}" ${l === liga ? "selected" : ""}>${esc(ligaN(l))}</option>`).join("")}</select></label>
      <label><span class="label">Posición (estimada)</span><select id="nkPos"><option value="">Todas</option>${Object.entries(POS).map(([k, v]) => `<option value="${k}" ${k === NKF.pos ? "selected" : ""}>${v}</option>`).join("")}</select></label>
      <label><span class="label">Minutos mín.</span><input type="number" id="nkMin" min="0" step="50" value="${+NKF.min}" style="width:110px"></label>
      <label><span class="label">Buscar</span><input type="search" id="nkQ" value="${esc(NKF.q)}" placeholder="Jugador o equipo"></label></div></div>
    <div class="block"><div class="block-h"><div><h3 class="h2">${esc(ligaN(liga))} ${esc(CTX.temp)}: ${rows.length} jugadores</h3><p class="sub">De ${nT} con Nivel Kerno · ordenados por Nivel Kerno · 0–100, 50 = jugador medio de la liga · rango del 80 %</p></div><span class="tag">Lectura</span></div>
      <div class="tw"><table><thead><tr><th class="n">#</th><th>Jugador</th><th>Equipo</th><th class="n">Min</th><th class="n">Nivel Kerno</th><th class="bar">0–100</th><th class="n">Producción</th><th class="n">Impacto</th><th class="n">RAPM</th><th class="n">Pts/p</th><th>Estilo</th><th>Confianza</th><th></th></tr></thead><tbody>
      ${rows.slice(0, NKF.ver).map((r, i) => `<tr class="go${r.liga === CTX.liga && r.team_id === CTX.id ? " sel" : ""}" data-k="${esc(r.k)}" tabindex="0"><td class="n">${i + 1}</td><td><div class="who"><b>${esc(r.nombre)}</b><span>${POS[r.pos3] || "s/d"}${r.division && r.division !== "única" ? ` · ${esc(r.division)}` : ""}</span></div></td><td>${esc(r.equipo)}</td><td class="n">${Math.round(r.min)}</td>
        <td class="n"><b>${Math.round(r.nk)}</b> <span class="rng">[${Math.round(r.nk_lo)}–${Math.round(r.nk_hi)}]</span></td><td>${nkbar(r.nk, r.nk_lo, r.nk_hi)}</td><td class="n">${ok(r.prod) ? Math.round(r.prod) : "—"}</td><td class="n">${ok(r.imp) ? Math.round(r.imp) : "—"}</td><td class="n">${ok(r.rapm) ? sgn(r.rapm, 1) : "—"}</td><td class="n">${fmt(r.pts_pg, 1)}</td><td>${estSpan(r.eu, r.eu_i)}</td><td>${confHTML(r)}</td>
        <td><button class="btn quiet" type="button" style="min-height:28px;padding:3px 9px" data-lista="${esc(r.k)}">${enLista(r.k) ? "En la lista" : "+ Lista"}</button></td></tr>`).join("")}
      </tbody></table></div>${rows.length > NKF.ver ? `<div><button class="btn quiet" type="button" data-act="nkmas">Ver 60 más (${NKF.ver} de ${rows.length})</button></div>` : ""}
      <p class="note">Las filas de tu equipo van resaltadas. Un jugador que juega en dos equipos aparece con cada uno. Pulsa una fila para abrir su ficha.</p></div>${pie(`${ligaN(liga)} ${CTX.temp}`)}`;
};
const guardarNKF = () => LS.set("kb.nkf", JSON.stringify(NKF));

// ---- Lista corta y comparativa
VISTAS.lista = async (tk) => {
  const a = LISTA.get();
  if (!a.length) { V().innerHTML = `<div class="block"><h2 class="h2">La lista corta está vacía</h2><p class="note">Añade jugadores desde «Nivel Kerno de la liga» o desde la ficha de un jugador. Se guarda solo en este navegador.</p>
      <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn" type="button" data-go="nk-liga">Nivel Kerno de la liga</button><button class="btn sec" type="button" data-act="buscar">Buscar un jugador</button></div></div>`; return; }
  V().innerHTML = cargando("Cargando la lista");
  try { await Promise.all([...new Set(a.map((x) => x.temp))].map(temporada)); } catch (e) { if (vigente(tk)) V().innerHTML = fallo(e); return; }
  if (!vigente(tk)) return;
  const sel = a.filter((x) => x.cmp).slice(0, 3), rows = sel.map((x) => porClave(x.k)).filter(Boolean), cls = ["s1", "s2", "s3"];
  const ms = [["Nivel Kerno", "", ["NK", "PROD", "IMP"]], ...GRUPOS];
  const comp = rows.length ? `<div class="block"><div class="block-h"><div><h3 class="h2">Comparativa</h3><p class="sub">Cada jugador frente a su liga y temporada · Nivel Kerno con su rango; el resto, percentil</p></div><span class="tag">Lectura</span></div>
      <div class="legend">${rows.map((r, i) => `<span><i style="background:var(--${cls[i]})"></i>${esc(r.nombre)} · ${esc(r.equipo)} ${esc(r.T.temp)}</span>`).join("")}</div>
      <div class="prof">${ms.map(([n, , mm]) => `<div class="g"><span>${n}</span></div>` + mm.map((m) => { const es = rows.map((r) => est(r, m));
        const bar = `<div class="pbar multi">${es.map((e, i) => (e ? `<span class="b ${cls[i]}" style="top:${5 + i * 11}px;left:${e.pl.toFixed(1)}%;width:${Math.max(0.6, e.ph - e.pl).toFixed(1)}%"></span><span class="p ${cls[i]}" style="top:${2 + i * 11}px;left:${e.p.toFixed(1)}%"></span>` : "")).join("")}</div>`;
        return `<div class="m">${M[m].n}</div>${bar}<div class="val">${es.map((e, i) => `<span style="display:inline-flex;align-items:center;gap:4px;margin-left:8px"><i style="width:8px;height:3px;background:var(--${cls[i]});display:inline-block"></i>${e ? fmtM(m, e.v) : "—"}</span>`).join("")}</div>`; }).join("")).join("")}
        <div></div><div class="axis"><span>0</span><span>25</span><span>50</span><span>75</span><span>100</span></div><div></div></div></div>` : `<p class="note">Marca hasta tres jugadores para compararlos.</p>`;
  V().innerHTML = `<div class="block"><div class="block-h"><div><h3 class="h2">${a.length} ${a.length === 1 ? "jugador" : "jugadores"} en la lista corta</h3><p class="sub">Marca hasta tres para compararlos</p></div></div>
    <div class="tw"><table><thead><tr><th>Comparar</th><th>Jugador</th><th class="n">Temporada</th><th class="n">Nivel Kerno</th><th class="n">Producción</th><th class="n">Impacto</th><th>Confianza</th><th></th></tr></thead><tbody>
    ${a.map((x) => { const r = porClave(x.k);
      return `<tr><td><label class="check"><input type="checkbox" data-cmp="${esc(x.k)}" ${x.cmp ? "checked" : ""} ${!x.cmp && sel.length >= 3 ? "disabled" : ""}><span class="sr">Comparar ${esc(x.nombre)}</span></label></td>
        <td><div class="who"><b>${esc(x.nombre)}</b><span>${esc(x.equipo)} · ${esc(LIGA_C[x.liga] || x.liga)}</span></div></td><td class="n">${esc(x.temp)}</td><td class="n">${r && ok(r.nk) ? `<b>${Math.round(r.nk)}</b> <span class="rng">[${Math.round(r.nk_lo)}–${Math.round(r.nk_hi)}]</span>` : "—"}</td><td class="n">${r && ok(r.prod) ? Math.round(r.prod) : "—"}</td><td class="n">${r && ok(r.imp) ? Math.round(r.imp) : "—"}</td><td>${r && ok(r.nk) ? confHTML(r) : "—"}</td>
        <td style="white-space:nowrap"><button class="btn quiet" type="button" style="min-height:28px;padding:3px 9px" data-k="${esc(x.k)}">Ficha</button> <button class="btn quiet" type="button" style="min-height:28px;padding:3px 9px" data-quitar="${esc(x.k)}">Quitar</button></td></tr>`; }).join("")}
    </tbody></table></div></div>${comp}${pie("varias temporadas")}`;
};

// ---- Los seis estilos
const CORTO_R = { ritmo: "Ritmo", triple: "3PAr", esquina: "Esquina", aro: "Aro", tiros_libres: "FTr", autocreacion: "Sin asistencia", asistencia: "AST%", reb_ofensivo: "Reb. of.", perdidas: "TOV%", robos: "Robos", tapones: "Tapones", faltas: "Faltas" };
VISTAS["es-estilos"] = async (tk) => {
  V().innerHTML = cargando("Leyendo los estilos");
  try { await Promise.all([equipos(), estilosClubes()]); } catch (e) { if (vigente(tk)) V().innerHTML = fallo(e); return; }
  if (!vigente(tk)) return;
  const t = CTX.temp, ligas = LIGAS.filter((l) => eqFilas(t, l).length);
  const cuenta = (l) => { const c = [0, 0, 0, 0, 0, 0]; let n = 0; eqFilas(t, l).forEach((r) => { const x = estiloClub(t, l, r.id); if (x && x.u) { c[x.u[0]]++; n++; } }); return { c, n }; };
  const ejemplos = (k) => { const out = []; ligas.forEach((l) => eqFilas(t, l).forEach((r) => { const x = estiloClub(t, l, r.id); if (x && x.u && x.u[0] === k) out.push({ r, p: x.u[1], l }); })); return out.sort((a, b) => b.p - a.p).slice(0, 4); };
  V().innerHTML = `<div class="block"><div class="block-h"><div><h3 class="h2">Seis estilos, una sola taxonomía</h3><p class="sub">Los mismos seis estilos de Kerno Analytics · cada rasgo medido frente a su propia liga vasca</p></div><span class="tag">Lectura</span></div>
      <p class="note" style="font-size:15px;color:var(--text-2)">Un mismo nombre describe a un equipo y a un jugador. Doce rasgos (ritmo, triple, esquina, aro, tiros libres, creación propia, pase, rebote ofensivo, pérdidas, robos, tapones y faltas) se convierten en puntuación normal por rangos <b>dentro de su liga y temporada</b>, y se asignan con la misma mezcla de seis componentes del sitio general. Un equipo «Spacing» de Cadete lo es frente a Cadete. Sin asistencias registradas (hasta 2025-26), creación propia y pase quedan fuera y el estilo se asigna con los rasgos observados.</p>
      <div class="estgrid">${ESTILOS.map((e, k) => { const c = e.centroide || {}, rs = Object.entries(c).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 5), ej = ejemplos(k);
        return `<div class="estcard" style="--c:${EST_COL[k]}"><h4><i class="estsw" style="background:${EST_COL[k]}"></i>${esc(e.nombre)} <span class="rng">· ${esc(e.rol_jugador || "")}</span></h4><p>${esc(e.equipo || e.definicion)}</p><p class="note">${esc(e.jugador || "")}</p>
          <div class="rasgos">${rs.map(([kk, v]) => `<span class="${v > 0.25 ? "up" : v < -0.25 ? "dn" : ""}">${esc(CORTO_R[kk] || kk)} ${v > 0 ? "↑" : "↓"}</span>`).join("")}</div>
          ${ej.length ? `<p class="note">En ${esc(t)}: ${ej.map((o) => `${esc(o.r.eq)} (${esc(LIGA_C[o.l])}, ${Math.round(100 * o.p)} %)`).join(" · ")}</p>` : ""}</div>`; }).join("")}</div></div>
    <div class="block"><div class="block-h"><div><h3 class="h2">Cómo juega cada liga en ${esc(t)}</h3><p class="sub">Equipos por estilo principal · ${esc(t)}</p></div><span class="tag dato">Dato</span></div>
      <div class="tw"><table><thead><tr><th>Liga</th><th class="n">Equipos</th><th>Reparto</th>${ESTILOS.map((e, k) => `<th class="n"><i class="estsw" style="background:${EST_COL[k]}"></i>${esc(e.nombre)}</th>`).join("")}</tr></thead><tbody>
      ${ligas.map((l) => { const { c, n } = cuenta(l); return `<tr class="${l === CTX.liga ? "sel" : ""}"><td>${esc(ligaN(l))}</td><td class="n">${n}</td><td style="min-width:200px"><div class="reparto">${c.map((x, k) => (x ? `<i style="width:${(100 * x / (n || 1)).toFixed(1)}%;background:${EST_COL[k]}" title="${esc(ESTILOS[k].nombre)}: ${x}"></i>` : "")).join("")}</div></td>${c.map((x) => `<td class="n">${x || "·"}</td>`).join("")}</tr>`; }).join("")}
      </tbody></table></div></div>
    <div class="block"><div class="block-h"><div><h3 class="h2">Equipos de ${esc(ligaN(CTX.liga))} ${esc(t)}</h3><p class="sub">Estilo principal, claridad y reparto entre los seis</p></div></div>
      <div class="tw"><table><thead><tr><th>Equipo</th><th>Estilo</th><th class="n">Claridad</th><th>Reparto</th></tr></thead><tbody>
      ${eqFilas(t, CTX.liga).map((r) => ({ r, x: estiloClub(t, CTX.liga, r.id) })).filter((o) => o.x).sort((a, b) => a.x.u[0] - b.x.u[0] || b.x.u[1] - a.x.u[1]).map(({ r, x }) => `<tr class="${r.id === CTX.id ? "sel" : ""}"><td>${esc(r.eq)}</td><td>${estSpan(x.u[2], x.u[0])}</td><td class="n">${Math.round(100 * x.u[1])} %</td><td style="min-width:220px">${Array.isArray(x.pr) ? `<div class="reparto">${x.pr.map((p, k) => (p >= 0.01 ? `<i style="width:${(100 * p).toFixed(1)}%;background:${EST_COL[k]}" title="${esc(ESTILOS[k].nombre)}: ${Math.round(100 * p)} %"></i>` : "")).join("")}</div>` : ""}</td></tr>`).join("")}
      </tbody></table></div><p class="note">Claridad: probabilidad del estilo principal. 80 % o más, «puro»; si el segundo pasa del 25 %, mezcla de dos.</p></div>${pie(t)}`;
};

// ---- Cómo leer y método del Nivel Kerno
VISTAS["como-leer"] = () => {
  V().innerHTML = `
    <div class="block"><div class="block-h"><h3 class="h2">Toda cifra se lee frente a su liga</h3></div>
      <p class="note" style="font-size:15px;color:var(--text-2)">Kerno Basque Analytics tiene la misma tipología que Kerno Analytics · Equipos sobre cuatro ligas de la Federación Vasca: Primera y Segunda Nacional, Junior y Cadete masculinos. No hay puente de normalización entre ellas ni con las ligas profesionales, así que <b>cada cifra se lee frente a su propia liga y temporada</b>: 50 = la media de su liga.</p>
      <div class="tw"><table><thead><tr><th>Concepto</th><th>Cómo se lee</th></tr></thead><tbody>
        <tr><td>Escala 0–100</td><td>50 + 50 · tanh(z / 2), con z = (valor − media de su liga) / desviación típica en las ligas vascas. 73 es una desviación típica por encima; 27, una por debajo; 88, dos. Los cambios (efectos X → Y, diferencias) se leen en puntos de esa escala con signo. El valor original aparece al pasar el ratón, y en las herramientas de detalle con el selector «Originales».</td></tr>
        <tr><td>Nivel Kerno</td><td>Producción e impacto del jugador frente a su liga en la escala 0–100, con su rango del 80 %. Ver «Nivel Kerno: método».</td></tr>
        <tr><td>Nivel Kerno de la plantilla</td><td>Media del Nivel Kerno de sus jugadores (100+ minutos), ponderada por minutos, frente al club medio de su liga (= 50).</td></tr>
        <tr><td>Percentil</td><td>Posición frente a los jugadores de su liga y temporada con 100+ minutos: 80 = supera al 80 %. Donde menos es mejor (pérdidas, rating defensivo, faltas) la barra ya está invertida: a la derecha siempre es mejor.</td></tr>
        <tr><td>Color</td><td>Azul (Lake): 60 o más. Arcilla (Clay): 40 o menos. Verde Racing o gris Sage: zona media o métricas de estilo. El color siempre acompaña a una cifra.</td></tr>
        <tr><td>Estilo</td><td>Los seis estilos del sitio general (Pistons, Isolation, Old-School, Spacing, Circulación, Pintura) con los rasgos medidos frente a su liga. Describe cómo juega, no cuánto vale.</td></tr>
        <tr><td>Temporada</td><td>Todas las fases de la temporada juntas (en Junior y Cadete, las dos divisiones): en las herramientas de detalle aparece como «Regular» y «Total», con el mismo contenido. El detalle por fase y división está en Federación Vasca.</td></tr>
        <tr><td>Tiempos muertos y stops</td><td>Del jugada a jugada de cada partido: tiempos muertos pedidos por el equipo, parcial en los 2 minutos anteriores y siguientes, primera posesión tras el tiempo muerto, y posesiones del rival sin puntos. Están en el informe de equipo (sección «Huella del entrenador» y «Defensa»).</td></tr>
        <tr><td>Entrenadores</td><td>Los que tienen licencia de primer entrenador en el equipo: la Federación no publica quién dirige cada partido.</td></tr>
        <tr><td>Posición</td><td>Exterior, alero o interior estimada con su perfil estadístico (regresión entrenada con las ligas FEB y la ACB): la Federación no la publica.</td></tr>
        <tr><td>Cobertura</td><td>Jugada a jugada desde 2022-23. De 2018-19 a 2021-22 solo hay calendario, resultados y plantillas (Federación Vasca). Asistencias registradas en 2026-27; tapones en parte de 2025-26 y en 2026-27: donde la mesa no las registra, sus métricas quedan vacías.</td></tr>
      </tbody></table></div></div>
    <div class="callout"><span class="label">Dónde termina lo que sabemos</span><p>Sin edad, altura ni posición oficial, sin datos de coste y sin vídeo. No hay simulador de fichajes ni proyección multiliga: un 70 en Cadete no se traduce a Primera Nacional. En una temporada en curso con pocas jornadas, los rangos son anchos a propósito.</p></div>${pie("método")}`;
};
VISTAS["nk-metodo"] = () => {
  V().innerHTML = `
    <div class="block"><div class="block-h"><div><h3 class="h2">Nivel Kerno vasco</h3><p class="sub">Nace del Nivel Kerno general: nivel e impacto con su rango · medido dentro de cada liga vasca</p></div><span class="tag">Método</span></div>
      <p class="note" style="font-size:15px;color:var(--text-2)">El Nivel Kerno general es el percentil esperado de producción de un jugador en su liga, acompañado del Impacto (cambio del equipo con él en pista). Aquí no hay puente entre ligas, así que se construye <b>dentro de cada liga y temporada</b> con dos capas, ambas en la misma escala que el resto del sitio.</p>
      <div class="tw"><table><thead><tr><th>Capa</th><th>Métricas</th><th>Cómo se calcula</th></tr></thead><tbody>
        <tr><td><b>Producción</b></td><td>PER · Win Shares por 40 · Game Score por 40 · PIE</td><td>Cada métrica se contrae hacia la media de su liga según los minutos ((m·x + k·μ) / (m + k), k = 300 min) y se convierte en puntuación normal por rangos frente a los jugadores de su liga (ponderados por minutos). Producción = media de las cuatro.</td></tr>
        <tr><td><b>Impacto</b></td><td>RAPM (jugada a jugada, ridge) · on/off ajustado por muestra</td><td>Igual: contracción y puntuación normal por rangos. Impacto = media de las dos.</td></tr>
        <tr><td><b>Nivel Kerno</b></td><td>0,6 · Producción + 0,4 · Impacto</td><td>Re-estandarizado a su liga (media 0, desviación 1, ponderado por minutos) y llevado a 0–100: 50 + 50 · tanh(z / 2). Sin jugada a jugada, solo Producción.</td></tr>
        <tr><td><b>Rango del 80 %</b></td><td>z ± 1,2816 · DT</td><td>DT = √(k / (m + k)): con 300 minutos, ±0,9 desviaciones; con 900, ±0,64. Mide cuánto puede moverse la lectura con más minutos.</td></tr>
        <tr><td><b>Confianza</b></td><td>Ancho del rango</td><td>Hasta 25 puntos de la escala, alta; hasta 45, moderada; más, baja.</td></tr>
      </tbody></table></div>
      <p class="note">Asistencias y tapones entran en PER, Win Shares y PIE solo donde la mesa los registra; donde no, con valor 0 para todos los jugadores de la liga, de modo que la comparación dentro de la temporada sigue siendo justa.</p></div>
    <div class="callout"><span class="label">Qué no es</span><p>No es una proyección a otra liga ni un valor de mercado. No mide la defensa sin balón más allá de lo que recoge el marcador con él en pista. Con menos de 300 minutos, léelo con su rango.</p></div>${pie("método")}`;
};

// ---------------------------------------------------------------------------------------------- búsqueda global
let BUS = { res: [], i: 0 };
async function abrirBusqueda() {
  $("search").hidden = false; $("searchIn").value = ""; $("searchRes").innerHTML = ""; $("searchIn").focus();
  $("searchHint").textContent = `${CTX.temp} · las cuatro ligas vascas · cargando…`;
  try { await temporada(CTX.temp); } catch (e) { $("searchHint").textContent = "No se pudieron cargar los jugadores"; return; }
  $("searchHint").textContent = `${CTX.temp} · ${SEAS[CTX.temp].rows.length.toLocaleString("es-ES")} registros jugador-equipo`;
  buscar();
}
function cerrarBusqueda() { $("search").hidden = true; $("searchBtn").focus(); }
function buscar() {
  const T = SEAS[CTX.temp]; if (!T) return;
  const q = norm($("searchIn").value).trim().split(/\s+/).filter(Boolean);
  if (!T.idx) T.idx = T.rows.map((r) => [norm(r.nombre), r]);
  const res = q.length ? T.idx.filter(([n]) => q.every((p) => n.includes(p))).map(([, r]) => r).sort((a, b) => b.min - a.min).slice(0, 40) : [];
  BUS = { res, i: 0 };
  $("searchRes").innerHTML = res.map((r, i) => `<button type="button" role="option" aria-selected="${i === 0}" data-k="${esc(r.k)}"><b>${esc(r.nombre)}</b><span>${filaJug(r)}</span><em>${Math.round(r.min)}′</em></button>`).join("")
    || (q.length ? `<p class="note" style="padding:12px 14px">Sin resultados en ${esc(CTX.temp)}. Prueba con el apellido o cambia la temporada.</p>` : "");
}

// ---------------------------------------------------------------------------------------------- eventos
function cerrarRail() { $("rail").classList.remove("open"); $("railScrim").classList.remove("on"); $("menuBtn").setAttribute("aria-expanded", "false"); }
document.addEventListener("click", (e) => {
  const t = e.target;
  const go = t.closest("[data-go]"); if (go) { navegar(go.dataset.go); return; }
  if (t.closest("[data-lista]")) { const r = porClave(t.closest("[data-lista]").dataset.lista); if (r) { alternarLista(r); t.closest("[data-lista]").textContent = enLista(r.k) ? "En la lista" : "+ Lista"; } e.stopPropagation(); return; }
  if (t.closest("[data-quitar]")) { LISTA.set(LISTA.get().filter((x) => x.k !== t.closest("[data-quitar]").dataset.quitar)); ir("lista"); return; }
  if (t.closest("#searchRes [data-k]")) { const r = porClave(t.closest("[data-k]").dataset.k); cerrarBusqueda(); if (r) abrirFicha(r); return; }
  const kb = t.closest("[data-k]"); if (kb && !t.closest("input")) { const r = porClave(kb.dataset.k); if (r) abrirFicha(r); return; }
  const a = t.closest("[data-act]"); if (a) {
    const act = a.dataset.act, r = porClave(S.fk);
    if (act === "buscar") abrirBusqueda();
    else if (act === "nkmas") { NKF.ver += 60; ir("nk-liga"); }
    else if (act === "tray" && r) cargarTrayectoria(r);
    else if (act === "lista" && r) { alternarLista(r); a.textContent = enLista(r.k) ? "Quitar de la lista corta" : "Añadir a la lista corta"; }
    else if (act === "impacto" && r) { S.q = { t: r.T.temp, l: r.liga, e: r.team_id, j: r.player_id }; navegar("eq-impacto"); }
    else if (act === "informeq" && r) { CTX.liga = r.liga; CTX.id = r.team_id; CTX.temp = r.T.temp; guardarCtx(); pintarCtx(); pintarEnt(); publicarCtx(); navegar("eq-informe"); }
    return;
  }
  const ab = t.closest("#setEsc [data-v], #setAyu [data-v], #setTema [data-v]"); if (ab) {
    const id = ab.parentElement.id; if (id === "setEsc") CTX.escala = ab.dataset.v; else if (id === "setAyu") CTX.ayudas = ab.dataset.v === "1"; else { CTX.tema = ab.dataset.v; aplicarTema(); }
    guardarCtx(); pintarAjustes(); publicarCtx(); return;
  }
  if (!t.closest("#setPop") && !t.closest("#setBtn") && !$("setPop").hidden) { $("setPop").hidden = true; $("setBtn").setAttribute("aria-expanded", "false"); }
  if (t === $("search")) cerrarBusqueda();
});
document.addEventListener("change", (e) => {
  const t = e.target;
  if (t.id === "ctxClub") { const [l, id] = t.value.split("|"); CTX.liga = l; CTX.id = id; CTX.ent = ""; NKF.liga = ""; guardarCtx(); pintarCtx(); pintarEnt(); publicarCtx(); ir(S.route); }
  else if (t.id === "ctxEnt") {
    CTX.ent = t.value; const o = entActual();
    if (o && !o.et.some((x) => x.temp === CTX.temp)) { const ts = o.et.map((x) => x.temp).filter((x) => TEMPS.includes(x)); if (ts.length) { CTX.temp = ts[ts.length - 1]; toast(`${o.n}: temporada ${CTX.temp}`); } }
    guardarCtx(); pintarCtx(); pintarEnt(); publicarCtx(); ir(S.route);
  }
  else if (t.id === "ctxTemp") { CTX.temp = t.value; const o = entActual(); if (o && !o.et.some((x) => x.temp === CTX.temp)) CTX.ent = ""; guardarCtx(); pintarCtx(); pintarEnt(); publicarCtx(); ir(S.route); }
  else if (t.id === "nkLiga" || t.id === "nkPos" || t.id === "nkMin") { NKF[{ nkLiga: "liga", nkPos: "pos", nkMin: "min" }[t.id]] = t.value; NKF.ver = 60; guardarNKF(); ir("nk-liga"); }
  else if (t.dataset.cmp) { const a = LISTA.get(), x = a.find((y) => y.k === t.dataset.cmp); if (x) { x.cmp = t.checked; LISTA.set(a); } ir("lista"); }
});
document.addEventListener("input", (e) => { if (e.target.id === "nkQ") { NKF.q = e.target.value; guardarNKF(); clearTimeout(S.qT); S.qT = setTimeout(() => { ir("nk-liga"); requestAnimationFrame(() => { const i = $("nkQ"); if (i) { i.focus(); i.setSelectionRange(i.value.length, i.value.length); } }); }, 250); } });
document.addEventListener("keydown", (e) => {
  const enCampo = /^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement && document.activeElement.tagName);
  if (!$("search").hidden) {
    if (e.key === "Escape") { e.preventDefault(); cerrarBusqueda(); return; }
    if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); const bs = [...$("searchRes").querySelectorAll("button")]; if (!bs.length) return; BUS.i = (BUS.i + (e.key === "ArrowDown" ? 1 : -1) + bs.length) % bs.length; bs.forEach((b, i) => b.setAttribute("aria-selected", String(i === BUS.i))); bs[BUS.i].scrollIntoView({ block: "nearest" }); return; }
    if (e.key === "Enter" && BUS.res[BUS.i]) { e.preventDefault(); const r = BUS.res[BUS.i]; cerrarBusqueda(); abrirFicha(r); return; }
    return;
  }
  if (e.key === "Escape" && !$("setPop").hidden) { $("setPop").hidden = true; return; }
  if ((e.key === "/" && !enCampo) || (e.key.toLowerCase() === "k" && (e.metaKey || e.ctrlKey))) { e.preventDefault(); abrirBusqueda(); return; }
  if (e.key === "Enter" && document.activeElement && document.activeElement.matches("tr.go[data-k]")) { const r = porClave(document.activeElement.dataset.k); if (r) abrirFicha(r); }
});
$("searchIn").addEventListener("input", buscar);
$("searchClose").addEventListener("click", cerrarBusqueda);
$("searchBtn").addEventListener("click", abrirBusqueda);
$("backBtn").addEventListener("click", atras);
$("homeBtn").addEventListener("click", () => navegar("inicio"));
$("setBtn").addEventListener("click", () => { const p = $("setPop"); p.hidden = !p.hidden; $("setBtn").setAttribute("aria-expanded", String(!p.hidden)); });
$("menuBtn").addEventListener("click", () => { const o = !$("rail").classList.contains("open"); $("rail").classList.toggle("open", o); $("railScrim").classList.toggle("on", o); $("menuBtn").setAttribute("aria-expanded", String(o)); });
$("railScrim").addEventListener("click", cerrarRail);
window.addEventListener("hashchange", () => ir(location.hash.replace(/^#/, "").split("&")[0] || "inicio"));
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { if (CTX.tema === "sistema") { aplicarTema(); publicarCtx(); } });

// ---------------------------------------------------------------------------------------------- arranque
(async function arrancar() {
  aplicarTema(); pintarRail();
  V().innerHTML = cargando("Preparando Kerno Basque Analytics");
  try {
    [IDX] = await Promise.all([cargarJSON("quintetos/datos/indice.json"), equipos(), estilosClubes()]);
    TEMPS = Object.keys(IDX.temporadas || {}).sort().reverse();
    if (!TEMPS.includes(CTX.temp)) CTX.temp = TEMPS[0];
    await temporada(CTX.temp);
  } catch (e) { V().innerHTML = fallo(e); return; }
  pintarCtx(); pintarAjustes(); pintarEnt(); guardarCtx(); publicarCtx();
  ir(location.hash.replace(/^#/, "").split("&")[0] || "inicio");
})();
