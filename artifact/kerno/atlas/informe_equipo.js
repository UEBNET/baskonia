/* =====================================================================================================
   Kerno Analytics · Informe de equipo (A4) · v1.0 · 03-11-2026
   Pestaña «Informe equipo» del Atlas, antes de «Informe» (lectura de fichaje). Mismo documento, misma marca y misma
   mecánica que la lectura de fichaje (portada y página 01 idénticas, hojas A4, descarga PDF, HTML imprimible, pestaña
   nueva y nota del analista redactada en tono Kerno), con otro objeto: el estado de un equipo frente a su liga.

   Estructura: portada · 01 Kerno Analytics · 02 El equipo · 03 Conclusiones · 04 Ataque · 05 Defensa y rebote ·
   06 Rotación · 07 Quintetos · 08 Parejas y conexiones · 09 Jugadores · 10 Glosario · contraportada.

   Dos versiones del documento (selector en los controles):
   - A · Lectura: tablas cortas con su percentil frente a la liga, como la lectura de fichaje.
   - B · Pizarra: más visual: cada equipo de la liga como un punto, la pista con los quintetos, la red de pases dibujada.

   Datos (los mismos de «Equipos y quintetos», sin cálculos nuevos):
   - ../quintetos/datos/equipos (totales de equipo y rival, plantillas con su nivel L, entrenadores y estilo del club).
   - ../quintetos/datos/<temporada>/<liga> (rotación, on/off, RAPM, quintetos, parejas, tríos, asistencias).
   - Atlas: clubes y jugadores (estilo unificado), informe/<temporada> (medias por partido) y rol del simulador.
   No toca el informe de jugador: solo lee sus funciones públicas (descarga, PDF, fuentes, CSS de las hojas).

   v1.1 · 03-11-2026 (decisión del CEO): un equipo se lee siempre con la vara de SU liga, nunca trasladado a otra.
   Todas las escalas ±100 del informe tienen 0 = media de su liga y ±46 = una desviación típica de su liga:
     S = 100 · tanh(z / 2),  z = (valor − media de su liga) / DT de su liga   (misma forma que las escalas del artifact)
   con la media y la DT de lo que se compara: plantillas y Net frente a los equipos de su liga; nivel de cada jugador
   frente a los jugadores de su liga (ponderado por minutos); impacto (RAPM, ORAPM, DRAPM en su liga) frente a los
   jugadores de su liga; quintetos, tríos y parejas frente a las unidades de su liga. Es la «vara de destino» de la
   normalización v3.2 (cualquier liga a 0) aplicada a la propia liga. Ya no hay referencias a la Euroliga.
   Nuevo en 04: «Quién sostiene el ataque» (ORAPM en su liga), como «Quién sostiene la defensa» en 05.

   v1.2 · 03-11-2026: sección «El entrenador» tras «Rotación» (tras «Defensa» si no hay quintetos): cómo quiere jugar
   (ritmo, triple, pase, rebote ofensivo, presión, qué concede), cómo reparte los minutos (turnos, banquillo, cierres,
   jóvenes, tamaño, quinteto inicial) frente a los equipos de su liga, y su trayectoria en los datos (todas sus etapas,
   cada una con la vara de su liga) para separar su huella de la plantilla. Numeración de secciones según el orden real.
   ===================================================================================================== */
"use strict";
(function () {
  if (typeof ifPdf !== "function" || typeof ifCargarEq !== "function" || typeof cargarJSON !== "function") return;

  // ------------------------------------------------------------------------------------------- 0. utilidades
  const CONFK = (k) => { const x = window.KernoV41 && KernoV41.listo() && KernoV41.datos.prod.sellos[k]; return x ? ` · confianza ${x.confianza_es}` : ""; };   // v4.1 · confianza (F4)
  const $1 = (s) => document.querySelector(s);
  const E = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const ok = (v) => typeof v === "number" && isFinite(v);
  const N = (v, d = 1) => ifN(v, d), SG = (v, d = 1) => ifSg(v, d);
  const SG0 = (v, d = 1) => !ok(v) ? "–" : Math.abs(v) < 0.5 * Math.pow(10, -d) ? "±" + N(0, d) : SG(v, d);
  const PC = (v, d = 1) => ok(v) ? N(v, d) + " %" : "–";
  const ord = (n) => ok(n) ? `${n}.º` : "–";
  const ordA = (n) => ok(n) ? `${n}.ª` : "–";
  // nombres en mayúsculas (FEB y otras fuentes) → como se escriben; el resto, tal cual
  const caja = (n) => { const x = String(n || ""); return x === x.toUpperCase() && /\p{L}{3}/u.test(x) ? x.toLowerCase().replace(/(^|[\s'’\-(,.\/])(\p{L})/gu, (m, a, b) => a + b.toUpperCase()).replace(/(?<=\S\s)(De|Del|La|Las|Los|Y|Da|Do|Dos|Van|Von|Der)(?=\s)/g, (w) => w.toLowerCase()) : x; };
  const nom = (n) => ifNom(caja(n)), ape = (n) => ifApe(caja(n));
  const corta = (t, n) => { t = String(t || ""); return t.length > n ? t.slice(0, n - 1).trimEnd() + "…" : t; };
  const normQ = (t) => String(t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const cap = (s) => s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
  const LS = "cerno.informe.equipo.v1";
  const lsGet = () => { try { return JSON.parse(localStorage.getItem(LS) || "{}") || {}; } catch (e) { return {}; } };
  const lsSet = (o) => { try { localStorage.setItem(LS, JSON.stringify(o)); } catch (e) { /* sin almacenamiento */ } };
  const FASES = [["regular", "Liga regular"], ["playoffs", "Playoffs"], ["total", "Toda la temporada"]];
  const FNOM = { regular: "liga regular", playoffs: "playoffs", total: "toda la temporada" };
  const ROLN = { RESIDUAL: "Residual", PROFUNDIDAD: "Profundidad", ROTACION: "Rotación", TITULAR: "Titular", GO_TO_GUY: "Go-to-guy" };
  const POSL = { E: "Exterior", A: "Alero", I: "Interior" };
  const VERS = { A: "Lectura", B: "Pizarra" };
  const C = { ink: "#0F2E25", g7: "#3F4B45", g6: "#56625C", g5: "#707B75", g4: "#8F9993", g3: "#B2BAB5", g2: "#CFD5D0", g1: "#E3E7E2", paper: "#F3F4F0", up: "#2B6FBF", dn: "#D35C2A", neu: "#6550CC", s700: "#1F4A3D" };
  // estilos de juego en el informe de equipo (decisión del CEO, v1.5, 03-11-2026): colores de marca que no se confunden
  // con azul/naranja (mejor/peor) ni con violeta (rasgo de estilo), y sin rosa. Orden fijo de los 6 estilos unificados:
  // Kerno v2.0 (el latón no es una serie y los colores de estado no se reutilizan): Circulación Racing · Pintura Sage 600 ·
  // Spacing Jade · Old-School Olive · Pistons Racing 300 · Isolation Jade claro (relleno pálido con borde Jade).
  // Relleno, borde y color del texto sobre el relleno
  const EST_CORP = [{ f: "#0F2E25", s: "#F3F4F0", t: "#F3F4F0" }, { f: "#56625C", s: "#F3F4F0", t: "#F3F4F0" }, { f: "#12997A", s: "#F3F4F0", t: "#F3F4F0" },
    { f: "#7F8418", s: "#F3F4F0", t: "#F3F4F0" }, { f: "#7FA597", s: "#F3F4F0", t: "#0C1210" }, { f: "rgba(18, 153, 122,0.18)", s: "#12997A", t: "#0C1210" }];
  const SIN_EST = { f: "#B2BAB5", s: "#F3F4F0", t: "#0C1210" };
  const estC = (k) => (ok(k) && EST_CORP[k % EST_CORP.length]) || SIN_EST;
  const prov = (t) => !!(META && META.temporadas_provisionales && META.temporadas_provisionales.includes(t));
  const gmin = (l) => (l === "nba" || l === "gleague") ? 48 : 40;
  // vara de su liga: media y DT (ponderadas) de lo que se compara → escala ±100 con 0 = media de su liga
  function vara(pares) {
    const a = pares.filter(([v, w]) => ok(v) && ok(w) && w > 0); if (a.length < 3) return null;
    const W = a.reduce((x, [, w]) => x + w, 0), m = a.reduce((x, [v, w]) => x + v * w, 0) / W, sd = Math.sqrt(a.reduce((x, [v, w]) => x + w * (v - m) ** 2, 0) / W);
    return sd > 1e-9 ? { m, sd } : null;
  }
  const SV = (v, V) => ok(v) && V ? 100 * Math.tanh((v - V.m) / V.sd / 2) : null;

  // ------------------------------------------------------------------------------------------- 1. datos
  // 1a · evaluación de equipos (totales oficiales de equipo y rival, plantillas, entrenadores): el mismo fichero que «Evaluación»
  let EVX = null;
  async function ev() {
    if (EVX) return EVX;
    const raw = await ifCargarEq(); if (!raw || !raw.columnas) throw new Error("no se pudo cargar la evaluación de equipos");
    const Cn = raw.columnas;
    const F = raw.filas.map((f) => { const o = {}; Cn.forEach((c, i) => { o[c] = f[i]; }); return o; }).filter((o) => !String(o.id).includes(";")); // «A;B»: filas fusionadas del fichero, no son equipos
    const by = new Map(); F.forEach((r) => by.set(`${r.t}|${r.f}|${r.liga}|${r.id}`, r));
    const P = raw.plantillas || {}, Cl = raw.clubes || {};
    F.forEach((r) => { const p = P[r.k]; r.L = p && ok(p.L) ? p.L : null; const b = balDe(r, Cl, by); r.bw = b ? b.w : null; r.bl = b ? b.l : null; r.bsrc = b ? b.src : null; r.wp = b && b.w + b.l > 0 ? 100 * b.w / (b.w + b.l) : null; });
    EVX = { F, by, P, C: Cl };
    return EVX;
  }
  // balance: el oficial de la fase; si la fuente no lo publica (Euroliga, EuroCup), el de sus entrenadores o el total
  function balDe(r, Cl, by) {
    if (ok(r.w) && ok(r.l)) return { w: r.w, l: r.l, src: r.wl || "oficial" };
    if (r.f !== "playoffs") { const ent = (Cl[r.k] && Cl[r.k].ent) || []; let w = 0, l = 0, n = 0; ent.forEach((e) => { if (ok(e.w) && ok(e.l)) { w += e.w; l += e.l; n++; } }); if (n && w + l > 0) return { w, l, src: "entrenadores" }; }
    if (r.f === "playoffs") return null; // sin balance oficial de playoffs: no se sustituye por el de toda la temporada
    const tot = by.get(`${r.t}|total|${r.liga}|${r.id}`); if (tot && ok(tot.w) && ok(tot.l)) return { w: tot.w, l: tot.l, src: "total" };
    return null;
  }
  // 1b · datos de quintetos de una liga y temporada (mismo formato que «Equipos y quintetos»)
  const LIGD = new Map();
  const objs = (tab) => { if (!tab || !Array.isArray(tab.c)) return []; const c = tab.c, n = c.length; return tab.f.map((r) => { const o = {}; for (let i = 0; i < n; i++) o[c[i]] = r[i]; return o; }); };
  function prep(raw) {
    const D = { liga: raw.liga, temp: raw.temporada, eqn: Object.assign({}, raw.equipos_nombre || {}) };
    D.J = objs(raw.jugadores); D.on = objs(raw.on_off); D.Q = objs(raw.quintetos); D.T3 = objs(raw.trios); D.P = objs(raw.parejas);
    D.A = objs(raw.asistencias); D.E = objs(raw.efectos); D.EQ = objs(raw.equipos);
    D.Q.forEach((q) => { q.u = q.u.slice().sort((a, b) => a - b); }); D.T3.forEach((q) => { q.u = q.u.slice().sort((a, b) => a - b); });
    D.hasQ = D.Q.length > 0 && D.EQ.length > 0;
    return D;
  }
  // extras de equipo por liga y temporada (fichero aparte; si no existe, el informe sigue sin esos bloques)
  const EXD = new Map();
  function extrasD(t, l) {
    const k = `${t}/${l}`;
    if (!EXD.has(k)) EXD.set(k, cargarJSON(`../quintetos/datos/${t}/${l}.extras`).catch(() => null));
    return EXD.get(k);
  }
  function ligaD(t, l) {
    const k = `${t}/${l}`;
    if (!LIGD.has(k)) LIGD.set(k, cargarJSON(`../quintetos/datos/${t}/${l}`).then(prep).catch((e) => { LIGD.delete(k); throw e; }));
    return LIGD.get(k);
  }
  // umbral adaptativo de muestra (el de «Equipos y quintetos»)
  function umbral(vals, n, max, paso = 5, min = 0) { const a = vals.filter(ok).sort((x, y) => y - x); const v = a.length ? a[Math.min(n, a.length) - 1] : 0; return Math.max(min, Math.floor(Math.min(max, v) / paso) * paso); }
  // percentil frente a los equipos de su liga (0-100, 100 = el que más; con sentido −1, el que menos) y puesto
  function pctL(rows, k, v, dir) {
    const vals = rows.map((x) => x[k]).filter(ok); if (!ok(v) || vals.length < 3) return null;
    const d = dir === -1 ? -1 : 1; let a = -0.5; vals.forEach((x) => { const s = (v - x) * d; if (s > 1e-9) a += 1; else if (Math.abs(s) <= 1e-9) a += 0.5; });
    return Math.max(0, Math.min(100, 100 * a / (vals.length - 1)));
  }
  function rangoL(rows, k, v, dir) { const vals = rows.map((x) => x[k]).filter(ok); if (!ok(v) || !vals.length) return null; return 1 + vals.filter((x) => (dir === -1 ? x < v : x > v)).length; }
  const media = (rows, k) => { const v = rows.map((x) => x[k]).filter(ok); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };

  // métricas del equipo frente a su liga: [clave, nombre llano, sentido (1 más es mejor, −1 menos es mejor, 0 estilo), decimales, qué mide]
  const MET = {
    ataque: [["ortg", "Puntos por 100 posesiones", 1, 1, "Rating ofensivo: lo que anota cada 100 ataques."], ["efg", "Acierto de tiro (eFG%)", 1, 1, "Acierto de campo con el triple valiendo uno y medio."],
      ["tov", "Pérdidas", -1, 1, "Balones perdidos por cada 100 posesiones."], ["orb", "Rebote ofensivo", 1, 1, "Parte de sus fallos que recupera."], ["ftr", "Tiros libres provocados", 1, 1, "Tiros libres por cada 100 tiros de campo."],
      ["t3", "Acierto en triples", 1, 1, "Porcentaje de triples anotados."], ["t2", "Acierto en tiros de 2", 1, 1, "Porcentaje de tiros de dos anotados."], ["tl", "Acierto en tiros libres", 1, 1, "Porcentaje de tiros libres anotados."],
      ["t3r", "Peso del triple", 0, 1, "Triples por cada 100 tiros: es estilo, no calidad."], ["astr", "Canastas asistidas", 0, 1, "Parte de sus canastas que llegan tras pase: es estilo."], ["ritmo", "Ritmo", 0, 1, "Posesiones por partido: es estilo."]],
    defensa: [["drtg", "Puntos que encaja por 100 posesiones", -1, 1, "Rating defensivo: menos es mejor."], ["oefg", "Acierto que concede (eFG% rival)", -1, 1, "Calidad de los tiros que permite."],
      ["otov", "Pérdidas que fuerza", 1, 1, "Balones que roba o provoca por cada 100 posesiones rivales."], ["drb", "Rebote defensivo", 1, 1, "Parte de los fallos rivales que recoge."], ["oftr", "Tiros libres que concede", -1, 1, "Tiros libres rivales por cada 100 tiros rivales."],
      ["ot3", "Triples que concede (T3% rival)", -1, 1, "Acierto rival en triples: depende en parte de la suerte."], ["ot2", "Tiros de 2 que concede", -1, 1, "Acierto rival en tiros de dos."], ["stl", "Robos", 1, 1, "Robos por cada 100 posesiones rivales."],
      ["blk", "Tapones", 1, 1, "Tiros de dos rivales que tapona."], ["ot3r", "Triples que permite intentar", 0, 1, "Peso del triple en el rival: es estilo defensivo."]],
  };
  const FACT_OFF = ["efg", "tov", "orb", "ftr"], FACT_DEF = ["oefg", "otov", "drb", "oftr"];
  const metDe = (k) => [...MET.ataque, ...MET.defensa].find((m) => m[0] === k);

  // 1c · contexto completo del equipo (todo lo que pintan las hojas)
  async function contexto(s) {
    const X = await ev();
    const r = X.by.get(`${s.temp}|${s.fase}|${s.liga}|${s.eq}`);
    if (!r) return { error: "sin_fila" };
    const lg = X.F.filter((x) => x.t === s.temp && x.f === s.fase && x.liga === s.liga);
    const club = X.C[r.k] || null, pl = X.P[r.k] || null, at = BY.get(r.k) || null, t = s.temp, l = s.liga;
    const c = { s, r, lg, n: lg.length, club, pl, at, t, l, ligaNom: LIGAS[l] || ESC.ligaNom(l), ligaC: LC[l] || ESC.ligaCorto(l), nombre: r.eq || (at && at.nombre_club) || s.eq, prov: prov(t) || !!(club && club.prov) };
    // nivel de la plantilla frente a las plantillas de su liga (escala ±100, 0 = plantilla media de su liga)
    const lgL = lg.filter((x) => ok(x.L)); c.vEq = vara(lgL.map((x) => [x.L, 1]));
    c.SL = SV(r.L, c.vEq); c.rkPl = ok(r.L) ? rangoL(lgL, "L", r.L, 1) : null; c.nPl = lgL.length; c.pPl = ok(r.L) ? pctL(lgL, "L", r.L, 1) : null;
    c.vNet = vara(lg.map((x) => [x.net, 1]));
    // nivel de cada jugador frente a los jugadores de su liga (ponderado por minutos, 100 minutos o más)
    c.vJ = vara(JG.filter((j) => j.liga === l && j.temporada === t && (j.min || 0) >= 100).map((j) => [j.L, j.min]));
    // balance, puesto y victorias esperadas
    c.bal = ok(r.bw) ? { w: r.bw, l: r.bl, src: r.bsrc } : null;
    c.rkW = ok(r.wp) ? rangoL(lg.filter((x) => ok(x.wp)), "wp", r.wp, 1) : null; c.nW = lg.filter((x) => ok(x.wp)).length;
    c.rkN = rangoL(lg, "net", r.net, 1); c.pN = pctL(lg, "net", r.net, 1);
    c.py = ok(r.ortg) && ok(r.drtg) && ok(r.gp) ? r.gp * Math.pow(r.ortg, 14) / (Math.pow(r.ortg, 14) + Math.pow(r.drtg, 14)) : null;
    c.dPy = c.bal && ok(c.py) && c.bal.w + c.bal.l === r.gp ? c.bal.w - c.py : null;
    // métricas frente a su liga
    c.met = {}; [...MET.ataque, ...MET.defensa].forEach(([k, nm, dir, d, q]) => { const v = r[k]; c.met[k] = { k, nm, dir, d, q, v, m: media(lg, k), p: pctL(lg, k, v, dir === 0 ? 1 : dir), rk: rangoL(lg, k, v, dir === 0 ? 1 : dir), vals: lg.map((x) => [x[k], x === r]).filter((x) => ok(x[0])) }; });
    const juicio = Object.values(c.met).filter((m) => m.dir !== 0 && !["ortg", "drtg"].includes(m.k) && m.p != null).sort((a, b) => b.p - a.p);
    c.fuertes = juicio.filter((m) => m.p >= 60).slice(0, 3); c.debiles = juicio.slice().reverse().filter((m) => m.p <= 40).slice(0, 3);
    // estilo del club (Atlas, taxonomía unificada)
    const eus = EUS(); c.eu = at && ok(at.eu) && eus[at.eu] ? { ...eus[at.eu], k: at.eu, etiqueta: at.eu_etiqueta || eus[at.eu].nombre, p: at.eu_p, probs: at.eu_probs } : null;
    // entrenadores (con el estilo de su etapa si el Atlas lo tiene)
    const entA = (at && Array.isArray(at.entrenadores) ? at.entrenadores : []).filter(Boolean);
    // el nivel de cada etapa de entrenador sale del índice de club convertido: se compara con las etapas de su liga
    c.vEnt = vara(lg.flatMap((x) => ((X.C[x.k] && X.C[x.k].ent) || []).map((e) => [e.L, e.pj || 1])));
    c.ent = ((club && club.ent) || []).map((e, i) => { const a = entA.find((x) => x.entrenador_id === e.id) || entA[i] || null; return { ...e, eu: a ? a.eu_etiqueta : null, SL: SV(e.L, c.vEnt) }; });
    // historial del club (liga regular de cada temporada)
    const cc = club && club.club;
    c.hist = cc ? X.F.filter((x) => x.f === "regular" && X.C[x.k] && X.C[x.k].club === cc).sort((a, b) => a.t.localeCompare(b.t)).map((x) => { const a2 = BY.get(x.k); return { t: x.t, liga: x.liga, S: SV(x.L, vara(X.F.filter((y) => y.t === x.t && y.f === "regular" && y.liga === x.liga && ok(y.L)).map((y) => [y.L, 1]))), w: x.bw, l: x.bl, wp: x.wp, net: x.net, ent: ((X.C[x.k] || {}).ent || []).map((e) => e.n), eu: a2 ? a2.eu_etiqueta : null, prov: !!(X.C[x.k] || {}).prov }; }) : [];
    // quintetos, rotación y red de pases
    let D = null; try { D = await ligaD(t, l); } catch (e) { D = null; }
    c.D = D; c.T = D && D.hasQ ? vista(D, s.eq, s.fase) : null;
    c.pix = D ? new Map(D.J.map((p, i) => [String(p.player_id), i])) : new Map();
    // extras del jugada a jugada (bbstats/lineups/equipo_extras.py): tiempos muertos, quintetos iniciales y stops
    try { c.X = await extrasD(t, l); } catch (e) { c.X = null; }
    c.XE = c.X && c.X.equipos && c.X.equipos[s.eq] ? c.X.equipos[s.eq][s.fase] || null : null;
    if (c.T) { c.jug = await jugadores(D, c.T, at, t, c); c.sn = nombresCortos(c.jug); }
    else c.jug = await jugadoresSinQ(pl, at, t, c);
    // minutos mínimos para entrar en el informe: filtra lo individual (jugadores, rotación, parejas, quintetos, red); lo colectivo no cambia
    c.minMin = minMinEq(s); c.jugTodos = c.jug || []; c.nTodos = c.jugTodos.filter((j) => (j.min || 0) > 0 || (j.mpg || 0) > 0).length;
    if (c.minMin && c.jug) c.jug = c.jug.filter((j) => (j.min || 0) >= c.minMin);
    c.okI = c.minMin && c.T ? new Set(c.jug.map((j) => j.j)) : null;
    // nota del analista
    const n = lsGet()[claveNota(s)] || {}; c.nota = (n.fin || n.raw || "").trim();
    c.para = (s.para || "").trim() || "Dirección deportiva";
    // v4.0 (05-11-2026) · capa 4: Net proyectado de la plantilla frente a su liga y anclas de cada jugador (atlas/v40.js)
    c.v40 = null;
    try {
      if (window.CernoV40 && CernoV40.listo() && typeof SIMD !== "undefined" && SIMD && !SIMD.error && at && typeof simClub === "function") {
        const cs = simClub(at);
        if (cs) {
          const recs = (cs.plantilla || []).map((x) => SIMD.jug.get(x[0])).filter(Boolean);
          if (recs.length >= 7) {
            const lg = CernoV40.ligaT(SIM2, SIMD, l, t, 300), out = SIM2.minutosEquipo(recs, cs, 600), eq = CernoV40.netEquipo(out, cs, lg);
            const pl = CernoV40.anclasPlantilla(SIM2, out, cs, recs, null), porRec = new Map(), porPer = new Map(pl.map((x) => [x.persona, x]));
            (cs.plantilla || []).forEach((x) => { const r = SIMD.jug.get(x[0]); if (r) porRec.set(`${r.liga}|${r.temporada}|${r.pid}`, porPer.get(x[3]) || null); });
            const anDe = (j) => (j.jg ? porRec.get(`${j.jg.liga}|${j.jg.temporada}|${j.jg.pid}`) : null) || null;
            (c.jugTodos || []).forEach((j) => { j.an = anDe(j); });
            const nombres = new Map((cs.plantilla || []).map((x) => { const r = SIMD.jug.get(x[0]); return [x[3], r ? r.nombre : x[3]]; }));
            c.v40 = { eq, liga: CernoV40.ligaNet(lg, l), pl: pl.map((x) => ({ ...x, nombre: nombres.get(x.persona) || x.persona })), club: cs, n_plantilla: recs.length, escenario: cs.escenario || "" };
          }
        }
      }
    } catch (e) { console.error("v4.0:", e); c.v40 = null; }
    return c;
  }
  // vista de un equipo en una fase dentro de los datos de quintetos
  function vista(D, eq, fase) {
    const T = { row: D.EQ.find((r) => r.team_id === eq && r.fase === fase) || null, lgEQ: D.EQ.filter((r) => r.fase === fase) };
    if (!T.row) return null;
    T.ros = D.on.filter((r) => r.team_id === eq && r.fase === fase && (r.min_on || 0) > 0).sort((a, b) => (b.min_on || 0) - (a.min_on || 0));
    T.Q = D.Q.filter((r) => r.team_id === eq && r.fase === fase);
    T.pf = fase; T.P = D.P.filter((r) => r.team_id === eq && r.fase === fase);
    if (!T.P.length && fase === "playoffs") { T.pf = "total"; T.P = D.P.filter((r) => r.team_id === eq && r.fase === "total"); }
    T.T3 = D.T3.filter((r) => r.team_id === eq && r.fase === T.pf);
    T.A = D.A.filter((r) => r.team_id === eq && r.fase === fase);
    T.E = D.E.filter((r) => r.team_id === eq);
    // perfil de tiro del equipo y de la liga (suma de los tiros de sus jugadores en pista)
    const Z = ["aro", "corta", "media", "t3_esquina", "t3_frontal"];
    const tiros = (rows) => { const o = {}; Z.forEach((z) => { o[z] = [rows.reduce((a, x) => a + (x["fga_" + z] || 0), 0), rows.reduce((a, x) => a + (x["fgm_" + z] || 0), 0)]; }); return o; };
    T.tiro = tiros(T.ros); T.tiroL = tiros(D.on.filter((r) => r.fase === fase));
    // varas de su liga: impacto de los jugadores (300+ posesiones) y unidades con muestra (quintetos, tríos, parejas)
    const onL = D.on.filter((r) => r.fase === fase && (r.rapm_poss || 0) >= 300);
    T.vR = vara(onL.map((r) => [r.rapm, r.rapm_poss])); T.vO = vara(onL.map((r) => [r.orapm, r.rapm_poss])); T.vD = vara(onL.map((r) => [r.drapm, r.rapm_poss]));
    T.vQ = vara(D.Q.filter((q) => q.fase === fase && (q.poss || 0) >= 50).map((q) => [q.net_rtg_aj, 1]));
    T.vT3 = vara(D.T3.filter((q) => q.fase === T.pf && (q.poss || 0) >= 100).map((q) => [q.net_rtg_aj, 1]));
    T.vP = vara(D.P.filter((p) => p.fase === T.pf && (p.min || 0) >= 100).map((p) => [p.sinergia, 1]));
    return T;
  }
  // jugadores del equipo: on/off y RAPM (quintetos) + estilo, rol y medias por partido (Atlas)
  async function jugadores(D, T, at, t, c) {
    const ro = at ? (ROSTER.get(at.clave) || []) : [], byPid = new Map(ro.map((j) => [String(j.pid), j]));
    let IX = null; try { const DI = await ifCargar(t); IX = window.CernoInformeV3 && window.CernoInformeV3.indice ? window.CernoInformeV3.indice(DI, t) : null; } catch (e) { IX = null; }
    return T.ros.map((x) => {
      const p = D.J[x.j] || {}, jg = byPid.get(String(p.player_id)) || null, e = jg && IX ? IX.get(jKey(jg)) : null, b = e && e.b ? e.b : null;
      const gp = x.gp || (b && b.gp) || 1, rol = jg && typeof rolDe === "function" ? rolDe(jg) : null;
      return { x, p, jg, b, j: x.j, nombre: nom(p.nombre || (jg && jg.nombre) || "?"), ape: ape(p.nombre || (jg && jg.nombre) || "?"), pos: p.pos3 || (jg && jg.pos3) || null, edad: ok(p.edad) ? p.edad : jg && ok(jg.edad) ? jg.edad : null,
        L: ok(p.L) ? p.L : jg && ok(jg.L) ? jg.L : null, SL: SV(ok(p.L) ? p.L : jg ? jg.L : null, c.vJ),
        // impacto en su liga (RAPM del jugada a jugada de su competición), escala de su liga
        rapm: ok(x.rapm) ? x.rapm : null, orapm: ok(x.orapm) ? x.orapm : null, drapm: ok(x.drapm) ? x.drapm : null, rposs: x.rapm_poss || 0,
        // v4.0 (06-11-2026): el impacto de cada jugador es su valor v4.0 (RAPM multiliga con prior del perfil) en la escala ±100 de la vara
        Srapm: jg && ok(jg.rapm_el) ? ESC.S("rapm", jg.rapm_el, jg.temporada) : SV(x.rapm, T.vR), Sorapm: SV(x.orapm, T.vO), Sdrapm: SV(x.drapm, T.vD),
        gp, mpg: (x.min_on || 0) / gp, min: x.min_on || 0, tit: x.titular_partidos || 0, cie: x.cierra_partidos || 0, onoff: x.net_rtg_aj_onoff, clutch: x.clutch_min || 0,
        q: [x.pct_min_q1, x.pct_min_q2, x.pct_min_q3, x.pct_min_q4].map((v) => ok(v) ? (x.min_on || 0) * v / 100 / gp : 0),
        pts: b ? b.pts_pg : null, reb: b ? b.reb_pg : null, ast: b ? b.ast_pg : null, ts: b ? b.ts_pct : null,
        eu: jg && jg.eu_etiqueta ? jg.eu_etiqueta : null, euC: jg && ok(jg.eu) && EUS()[jg.eu] ? EUS()[jg.eu].color : null, euI: jg && ok(jg.eu) ? jg.eu : null,
        rol: rol ? rol.rol : null, rolEst: rol ? rol.est : true, astD: x.ast_dadas || 0, astR: x.ast_recibidas || 0, pr: x.pagerank_asistencias };
    });
  }
  // sin datos de quintetos: la plantilla de la evaluación (nombre, puesto, edad, minutos, nivel)
  async function jugadoresSinQ(pl, at, t, c) {
    if (!pl || !Array.isArray(pl.j)) return [];
    const ro = at ? (ROSTER.get(at.clave) || []) : [];
    return pl.j.map((a) => { const jg = ro.find((j) => normQ(j.nombre) === normQ(a[0])) || null; const rol = jg && typeof rolDe === "function" ? rolDe(jg) : null;
      return { nombre: nom(a[0]), ape: ape(a[0]), pos: a[1], edad: a[2], min: a[3], L: a[4], SL: SV(a[4], c.vJ), eu: jg ? jg.eu_etiqueta : null, euC: jg && ok(jg.eu) && EUS()[jg.eu] ? EUS()[jg.eu].color : null, euI: jg && ok(jg.eu) ? jg.eu : null, rol: rol ? rol.rol : null, rolEst: rol ? rol.est : true, rapm: null, Srapm: null }; }); // sin jugada a jugada de su liga no hay impacto en su liga
  }
  function nombresCortos(js) { const cnt = {}; js.forEach((o) => { cnt[o.ape] = (cnt[o.ape] || 0) + 1; }); const m = new Map(); js.forEach((o) => m.set(o.j, cnt[o.ape] > 1 ? `${o.nombre.charAt(0)}. ${o.ape}` : o.ape)); return m; }
  const snJ = (c, j) => (c.sn && c.sn.get(j)) || (c.D && c.D.J[j] ? ape(c.D.J[j].nombre) : "?");
  // quinteto escrito como «APELLIDO, NOMBRE / …» → índices de jugador y fila del quinteto
  function qDeNombres(c, txt) {
    if (!txt || !c.T) return null; const ns = String(txt).split(" / ").map((x) => normQ(x.trim()));
    const idx = ns.map((n) => { const o = (c.jugTodos || c.jug).find((j) => j.p && normQ(j.p.nombre) === n); if (o) return o.j; const i = c.D.J.findIndex((p) => normQ(p.nombre) === n && p.team_id === c.s.eq); return i >= 0 ? i : null; });
    if (idx.some((i) => i == null)) return null; const u = idx.slice().sort((a, b) => a - b), k = u.join("-");
    return { u: idx, q: c.T.Q.find((q) => q.u.join("-") === k) || null };
  }
  function claveNota(s) { return `${s.liga}|${s.temp}|${s.eq}`; }
  // minutos mínimos (en la temporada y fase elegidas) para que un jugador entre en el informe; 0 = todos
  function minMinEq(s) { const v = Math.round(+((s || st.ieq || {}).minMin) || 0); return v > 0 ? Math.min(v, 4000) : 0; }
  const notaMinEq = (c) => c.minMin ? ` Solo jugadores con ${c.minMin} minutos o más.` : "";

  // ------------------------------------------------------------------------------------------- 2. piezas gráficas (SVG, tinta fija: las hojas son papel)
  // percentil frente a la liga: barra 0–100 con la mediana marcada y el punto del equipo
  function barraP(p, o = {}) {
    const w = o.w || 150, h = 12, x = (v) => 4 + (w - 8) * v / 100;
    if (p == null) return `<span class="r3na">sin dato</span>`;
    const cl = o.neu ? C.neu : p >= 65 ? C.up : p <= 35 ? C.dn : C.ink;
    return `<svg class="ieq-pb" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" aria-hidden="true"><line x1="4" x2="${w - 4}" y1="6" y2="6" stroke="${C.g3}" stroke-width="1"/><line x1="${x(50)}" x2="${x(50)}" y1="1.5" y2="10.5" stroke="${C.g5}" stroke-width=".8" stroke-dasharray="1.5 1.5"/><line x1="${x(50)}" x2="${x(p)}" y1="6" y2="6" stroke="${cl}" stroke-width="2.4" opacity=".35"/><circle cx="${x(p)}" cy="6" r="4" fill="${cl}"/></svg>`;
  }
  // la liga como fila de puntos: cada equipo un punto gris; el equipo, en tinta. Mejor a la derecha (se invierte si menos es mejor)
  function tira(vals, o = {}) {
    const w = o.w || 300, h = o.h || 34, dir = o.dir === -1 ? -1 : 1, xs = vals.map((v) => v[0]);
    let lo = Math.min(...xs), hi = Math.max(...xs); if (hi - lo < 1e-9) { lo -= 1; hi += 1; } const pad = (hi - lo) * 0.06; lo -= pad; hi += pad;
    const X = (v) => 8 + (w - 16) * (dir === 1 ? (v - lo) / (hi - lo) : (hi - v) / (hi - lo)), y = 14;
    const med = (() => { const a = xs.slice().sort((p, q) => p - q), m = a.length >> 1; return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2; })();
    const me = vals.find((v) => v[1]), cl = o.neu ? C.neu : me && o.p != null ? (o.p >= 65 ? C.up : o.p <= 35 ? C.dn : C.ink) : C.ink;
    const dots = vals.filter((v) => !v[1]).map((v) => `<circle cx="${X(v[0]).toFixed(1)}" cy="${y}" r="3.2" fill="${C.g4}" fill-opacity=".55"/>`).join("");
    const lab = (v, a) => `<text x="${a === "s" ? 8 : w - 8}" y="${h - 2}" text-anchor="${a === "s" ? "start" : "end"}" class="ax">${E(v)}</text>`;
    return `<svg class="ieq-tira" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="${E(o.aria || "posición en su liga")}"><line x1="8" x2="${w - 8}" y1="${y}" y2="${y}" stroke="${C.g2}" stroke-width="1"/><line x1="${X(med)}" x2="${X(med)}" y1="${y - 8}" y2="${y + 8}" stroke="${C.g5}" stroke-width=".8" stroke-dasharray="1.5 1.5"/>${dots}${me ? `<circle cx="${X(me[0]).toFixed(1)}" cy="${y}" r="6" fill="${cl}" stroke="${C.paper}" stroke-width="1.5"/>` : ""}${o.izq ? lab(o.izq, "s") : ""}${o.der ? lab(o.der, "e") : ""}</svg>`;
  }
  // barras divergentes (sinergias, Net de quintetos, RAPM): [{nom, v, txt, sub}]
  function divergentes(items, o = {}) {
    const w = o.w || 330, rh = o.rh || 19, lw = o.lw || 128, vw = 44, bw = w - lw - vw, mid = lw + bw / 2, m = o.max || Math.max(1, ...items.map((x) => Math.abs(x.v || 0))), h = items.length * rh + 6;
    const rows = items.map((x, i) => { if (!x.nom && !x.txt) return ""; const y = 3 + i * rh, bwid = Math.max(1, Math.abs(x.v || 0) / m * (bw / 2 - 4)), pos = (x.v || 0) >= 0, col = x.neu ? C.neu : pos ? C.up : C.dn;
      return `${x.yo ? `<rect x="0" y="${y - 1}" width="${w}" height="${rh}" class="hlr"/>` : ""}<text x="0" y="${y + rh / 2 + 2}" class="nm">${E(x.nom)}${x.sub ? `<tspan class="sb"> ${E(x.sub)}</tspan>` : ""}</text><rect x="${pos ? mid : mid - bwid}" y="${y + 4}" width="${bwid}" height="${rh - 10}" fill="${col}"/><text x="${w}" y="${y + rh / 2 + 2}" text-anchor="end" class="vv" fill="${col === C.up ? C.s700 : col}">${E(x.txt)}</text>`; }).join("");
    return `<svg class="ieq-dv" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="${E(o.aria || "")}">${rows}<line x1="${mid}" x2="${mid}" y1="0" y2="${h}" stroke="${C.ink}" stroke-width=".8"/></svg>`;
  }
  // puntos con rango del 80 % en 0–100: [{nom, v, lo, hi, sub, yo}]
  function puntosRango(items, o = {}) {
    const w = o.w || 330, rh = o.rh || 19, lw = o.lw || 128, vw = 30, bw = w - lw - vw, h = items.length * rh + 14, X = (x) => lw + bw * Math.max(0, Math.min(1, x / 100));
    const ejes = [0, 25, 50, 75, 100].map((k) => `<line x1="${X(k)}" x2="${X(k)}" y1="2" y2="${h - 12}" class="${k === (o.ref ?? 50) ? "rf" : "tr"}"/><text x="${X(k)}" y="${h - 2}" text-anchor="middle" class="ax">${k}</text>`).join("");
    const rows = items.map((x, i) => { const y = 3 + i * rh; return `${x.yo ? `<rect x="0" y="${y - 1}" width="${w}" height="${rh}" class="hl"/>` : ""}<text x="0" y="${y + rh / 2 + 2}" class="nm">${E(x.nom)}${x.sub ? `<tspan class="sb"> ${E(x.sub)}</tspan>` : ""}</text>${ok(x.lo) && ok(x.hi) ? `<rect x="${X(x.lo)}" y="${y + 4}" width="${Math.max(2, X(x.hi) - X(x.lo))}" height="${rh - 9}" class="bd"/>` : ""}<circle cx="${X(x.v)}" cy="${y + rh / 2 - .5}" r="3.2" class="pt"/><text x="${w}" y="${y + rh / 2 + 2}" text-anchor="end" class="vv">${Math.round(x.v)}</text>`; }).join("");
    return `<svg class="ieq-pr" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="${E(o.aria || "")}">${ejes}${rows}</svg>`;
  }
  // la liga según la capa 4: Net proyectado de cada plantilla (punto y rango del 80 %) frente a la media de la liga
  function ligaV40(c) {
    const v = c.v40; if (!v || !v.liga || !v.liga.length) return "";
    const eqs = v.liga, m = Math.max(4, ...eqs.map((e) => Math.max(Math.abs(e.lo80), Math.abs(e.hi80)))), w = 690, rh = eqs.length > 16 ? 10.2 : 13, lw = 150, vw = 60, bw = w - lw - vw, h = eqs.length * rh + 16, X = (x) => lw + bw * (0.5 + x / (2 * m));
    const tk = [-m, -m / 2, 0, m / 2, m].map((k) => `<line x1="${X(k)}" x2="${X(k)}" y1="2" y2="${h - 12}" class="${k === 0 ? "rf" : "tr"}"/><text x="${X(k)}" y="${h - 2}" text-anchor="middle" class="ax">${SG0(k, 0)}</text>`).join("");
    const rows = eqs.map((e, i) => { const y = 3 + i * rh, yo = e.team === v.club.team; return `${yo ? `<rect x="0" y="${y - 1}" width="${w}" height="${rh}" class="hl"/>` : ""}<text x="0" y="${y + rh / 2 + 2}" class="nm">${E(e.nombre)}</text><rect x="${X(e.lo80)}" y="${y + 3}" width="${Math.max(2, X(e.hi80) - X(e.lo80))}" height="${rh - 7}" class="bd"/><circle cx="${X(e.net)}" cy="${y + rh / 2 - .5}" r="2.8" class="pt"/><text x="${w}" y="${y + rh / 2 + 2}" text-anchor="end" class="vv">${SG0(e.net, 1)}</text>`; }).join("");
    const svg = `<svg class="ieq-pr" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="La liga según la capa 4">${tk}${rows}</svg>`;
    const eq = v.eq, real = ok(c.r.net) ? c.r.net : null, dif = real != null ? real - eq.net : null;
    return `<div class="r3blk"><h3>Lo que proyectan las plantillas de ${E(c.ligaNom)} y lo que da ${E(c.nombre)}</h3>${svg}<p class="r3n">Net proyectado de cada plantilla (capa 4, v4.0): valor de cada jugador en una escala común a las 20 ligas, parejas y minutos del motor, encogido con la calibración (${N(eq.c, 2)}) aprendida en cambios de plantilla reales; punto y rango del 80 %, por 100 posesiones frente a la media de la liga. ${E(c.nombre)}: ${SG0(eq.net, 1)} (${ord(eq.puesto)} de ${eq.n})${real != null ? `; diferencia real ${SG0(real, 1)}, ${Math.abs(dif) < 2 ? "en línea con sus piezas" : dif > 0 ? `${N(dif, 1)} por encima de sus piezas` : `${N(-dif, 1)} por debajo de sus piezas`}` : ""}.${eq.n_sin_beta ? ` ${eq.n_sin_beta} jugador${eq.n_sin_beta > 1 ? "es" : ""} sin valor medido.` : ""}</p></div>`;
  }
  // barras simples desde cero: [{nom, v, txt, sub}]
  function barras(items, o = {}) {
    const w = o.w || 330, rh = o.rh || 20, lw = o.lw || 150, vw = 40, bw = w - lw - vw, m = o.max || Math.max(1, ...items.map((x) => x.v || 0)), h = items.length * rh + 4;
    return `<svg class="ieq-dv" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="${E(o.aria || "")}">${items.map((x, i) => { const y = 2 + i * rh; return `<text x="0" y="${y + rh / 2 + 2}" class="nm">${E(x.nom)}${x.sub ? `<tspan class="sb"> ${E(x.sub)}</tspan>` : ""}</text><rect x="${lw}" y="${y + 4}" width="${Math.max(1, (x.v || 0) / m * (bw - 4)).toFixed(1)}" height="${rh - 9}" fill="${x.col || C.ink}"/><text x="${w}" y="${y + rh / 2 + 2}" text-anchor="end" class="vv">${E(x.txt)}</text>`; }).join("")}</svg>`;
  }
  // la liga en un mapa: nivel de la plantilla (comparable entre ligas) frente a % de victorias; la recta, lo esperable por nivel
  function mapaLiga(c, o = {}) {
    const conWp = c.lg.filter((x) => ok(x.L) && ok(x.wp)).length >= 4, yk = conWp ? "wp" : "net"; c.mapaY = yk;
    const pts = c.lg.filter((x) => ok(x.L) && ok(x[yk])).map((x) => ({ x: SV(x.L, c.vEq), y: x[yk], me: x === c.r, eq: x.eq })); if (pts.length < 4) return "";
    const w = o.w || 690, h = o.h || 230, m = { l: 40, r: 14, t: 12, b: 30 }, pw = w - m.l - m.r, ph = h - m.t - m.b;
    let x0 = Math.min(...pts.map((p) => p.x)), x1 = Math.max(...pts.map((p) => p.x)); const px = Math.max(4, (x1 - x0) * 0.08); x0 -= px; x1 += px;
    const yv = pts.map((p) => p.y), y0 = conWp ? 0 : Math.floor(Math.min(...yv) / 5) * 5 - 5, y1 = conWp ? 100 : Math.ceil(Math.max(...yv) / 5) * 5 + 5;
    const X = (v) => m.l + (v - x0) / (x1 - x0) * pw, Y = (v) => m.t + (1 - (v - y0) / (y1 - y0)) * ph;
    const n = pts.length, mx = pts.reduce((a, p) => a + p.x, 0) / n, my = pts.reduce((a, p) => a + p.y, 0) / n, sxx = pts.reduce((a, p) => a + (p.x - mx) ** 2, 0), b = sxx ? pts.reduce((a, p) => a + (p.x - mx) * (p.y - my), 0) / sxx : 0, a0 = my - b * mx;
    const cl = (v) => Math.max(y0, Math.min(y1, v)), ticks = conWp ? [0, 25, 50, 75, 100] : Array.from({ length: Math.floor((y1 - y0) / 5) + 1 }, (_, i) => y0 + 5 * i).filter((v, i, a) => a.length <= 7 || v % 10 === 0);
    let g = ticks.map((v) => `<line x1="${m.l}" x2="${m.l + pw}" y1="${Y(v)}" y2="${Y(v)}" stroke="${v === 0 && !conWp ? C.g5 : C.g2}" stroke-width=".6"/><text x="${m.l - 6}" y="${Y(v) + 3}" text-anchor="end" class="ax">${conWp ? v + " %" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v)}</text>`).join("");
    const st = x1 - x0 > 120 ? 50 : 25; for (let v = Math.ceil(x0 / st) * st; v <= x1; v += st) g += `<line x1="${X(v)}" x2="${X(v)}" y1="${m.t}" y2="${m.t + ph}" stroke="${v === 0 ? C.g5 : C.g2}" stroke-width=".6" ${v === 0 ? 'stroke-dasharray="2 2"' : ""}/><text x="${X(v)}" y="${h - 16}" text-anchor="middle" class="ax">${v === 0 ? "media = 0" : (v > 0 ? "+" : "−") + Math.abs(v)}</text>`;
    g += `<line x1="${X(x0)}" y1="${Y(cl(a0 + b * x0))}" x2="${X(x1)}" y2="${Y(cl(a0 + b * x1))}" stroke="${C.g5}" stroke-width="1" stroke-dasharray="4 3"/>`;
    g += pts.filter((p) => !p.me).map((p) => `<circle cx="${X(p.x).toFixed(1)}" cy="${Y(p.y).toFixed(1)}" r="4" fill="${C.g4}" fill-opacity=".7"/>`).join("");
    const me = pts.find((p) => p.me); if (me) g += `<circle cx="${X(me.x)}" cy="${Y(me.y)}" r="7" fill="${C.ink}" stroke="${C.paper}" stroke-width="1.5"/><text x="${X(me.x) + (X(me.x) > w - 150 ? -11 : 11)}" y="${Y(me.y) + 3.5}" text-anchor="${X(me.x) > w - 150 ? "end" : "start"}" class="pn">${E(c.nombre)}</text>`;
    g += `<text x="${m.l + pw}" y="${h - 3}" text-anchor="end" class="ax">Nivel de la plantilla frente a su liga, de menos a más</text><text x="${m.l}" y="${h - 3}" class="ax">${conWp ? "% de victorias ↑" : "Diferencia por 100 posesiones ↑"}</text>`;
    c.esperado = me ? cl(a0 + b * me.x) : null;
    return `<svg class="ieq-map" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="Nivel de la plantilla frente a % de victorias">${g}</svg>`;
  }
  // minutos por partido de cada jugador; versión B: partidos por cuartos apilados
  function minutosSVG(js, gm, o = {}) {
    const w = o.w || 330, rh = o.rh || 17, lw = 96, rw = 30, bw = w - lw - rw, max = gm, h = js.length * rh + 22;
    const qc = [C.ink, C.g6, C.g4, C.s700];
    const rows = js.map((j, i) => { const y = 4 + i * rh; let x = lw; const seg = o.cuartos ? j.q.map((v, k) => { const ww = v / max * bw, r = `<rect x="${x.toFixed(1)}" y="${y + 3}" width="${Math.max(0, ww - .6).toFixed(1)}" height="${rh - 7}" fill="${qc[k]}"/>`; x += ww; return r; }).join("") : `<rect x="${lw}" y="${y + 3}" width="${(j.mpg / max * bw).toFixed(1)}" height="${rh - 7}" fill="${C.ink}"/>`;
      return `<text x="0" y="${y + rh / 2 + 2}" class="nm">${E(j.corto)}</text>${seg}<text x="${w}" y="${y + rh / 2 + 2}" text-anchor="end" class="vv">${N(j.mpg, 1)}'</text>`; }).join("");
    const ax = [0, 10, 20, 30, 40].filter((v) => v <= gm).map((v) => `<line x1="${lw + v / max * bw}" x2="${lw + v / max * bw}" y1="2" y2="${h - 16}" stroke="${C.g2}" stroke-width=".6"/><text x="${lw + v / max * bw}" y="${h - 6}" text-anchor="middle" class="ax">${v}'</text>`).join("");
    return `<svg class="ieq-mn" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="Minutos por partido">${ax}${rows}</svg>${o.cuartos ? `<p class="ieq-ley">${["1.er cuarto", "2.º cuarto", "3.er cuarto", "4.º cuarto"].map((t, k) => `<span><i style="background:${qc[k]}"></i>${t}</span>`).join("")}</p>` : ""}`;
  }
  // media pista con un quinteto: exteriores arriba, aleros en las alas, interiores cerca del aro
  function pista(js, o = {}) {
    const w = o.w || 300, h = o.h || 196, cx = w / 2, aro = h - 26;
    const ord5 = js.slice().sort((a, b) => ({ E: 0, A: 1, I: 2 }[a.pos] ?? 1) - ({ E: 0, A: 1, I: 2 }[b.pos] ?? 1));
    const P = [[cx - 62, 42], [cx + 62, 42], [cx - 112, 112], [cx + 112, 112], [cx, 132]];
    const nodos = ord5.map((j, i) => { const [x, y] = P[i] || [cx, 90]; const ec = estC(j.euI); return `<circle cx="${x}" cy="${y}" r="13" fill="${ec.f}" stroke="${ec.s}" stroke-width="1.5"/><text x="${x}" y="${y + 3.5}" text-anchor="middle" class="pp" fill="${ec.t}" style="fill:${ec.t}">${E(j.pos || "–")}</text><text x="${x}" y="${y + 27}" text-anchor="middle" class="pn">${E(j.corto)}</text><text x="${x}" y="${y + 37}" text-anchor="middle" class="ax">${E(j.sub || "")}</text>`; }).join("");
    return `<svg class="ieq-pista" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="Quinteto en pista"><rect x="1" y="1" width="${w - 2}" height="${h - 2}" fill="none" stroke="${C.g3}"/><path d="M ${cx - 108} ${h - 1} L ${cx - 108} ${aro - 108} A 108 108 0 0 1 ${cx + 108} ${aro - 108} L ${cx + 108} ${h - 1}" fill="none" stroke="${C.g3}"/><rect x="${cx - 34}" y="${h - 76}" width="68" height="75" fill="none" stroke="${C.g3}"/><circle cx="${cx}" cy="${aro}" r="5" fill="none" stroke="${C.g5}"/>${nodos}</svg>`;
  }
  // red de pases: jugadores en círculo, grosor = asistencias entre ellos, tamaño = asistencias dadas y recibidas
  function redSVG(c, o = {}) {
    const w = o.w || 330, h = o.h || 300, cx = w / 2, cy = h / 2, R = Math.min(w, h) / 2 - 42;
    const js = c.jug.filter((j) => j.astD + j.astR > 0).slice(0, 10), pos = new Map();
    js.forEach((j, i) => { const a = -Math.PI / 2 + 2 * Math.PI * i / js.length; pos.set(j.j, [cx + R * Math.cos(a), cy + R * Math.sin(a), a]); });
    const ed = c.T.A.filter((a) => pos.has(a.p) && pos.has(a.r)).sort((a, b) => b.ast - a.ast).slice(0, 16), mx = Math.max(1, ...ed.map((a) => a.ast)), mn = Math.max(1, ...js.map((j) => j.astD + j.astR));
    const lin = ed.map((a, i) => { const [x1, y1] = pos.get(a.p), [x2, y2] = pos.get(a.r); return `<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" stroke="${i < 3 ? C.ink : C.g4}" stroke-opacity="${i < 3 ? .85 : .55}" stroke-width="${(0.8 + 4.2 * a.ast / mx).toFixed(2)}"/>`; }).join("");
    const nod = js.map((j) => { const [x, y, a] = pos.get(j.j), r = 6 + 9 * Math.sqrt((j.astD + j.astR) / mn), lx = x + (r + 6) * Math.cos(a), ly = y + (r + 6) * Math.sin(a) + 3, an = Math.cos(a) > 0.25 ? "start" : Math.cos(a) < -0.25 ? "end" : "middle";
      const ec = estC(j.euI);
      return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${r.toFixed(1)}" fill="${ec.f}" stroke="${ec.s}" stroke-width="1.5"/><text x="${lx.toFixed(1)}" y="${(Math.sin(a) > 0.6 ? ly + 4 : Math.sin(a) < -0.6 ? ly - 4 : ly).toFixed(1)}" text-anchor="${an}" class="pn">${E(j.corto)}</text>`; }).join("");
    return `<svg class="ieq-red" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="Red de pases">${lin}${nod}</svg>`;
  }
  // evolución del club: nivel de la plantilla por temporada (escala ±100), con su balance escrito debajo
  function evolSVG(hist, t0, o = {}) {
    const H0 = hist.filter((x) => x.S != null); if (H0.length < 2) return `<p class="r3n">Solo hay una temporada de este club en los datos.</p>`;
    const w = o.w || 330, h = o.h || 150, l = 30, r = 14, t = 16, b = 36, xs = (i) => l + (w - l - r) * i / (H0.length - 1);
    const vs = H0.map((x) => x.S), lo = Math.min(-60, ...vs) - 5, hi = Math.max(60, ...vs) + 5, ys = (v) => t + (h - t - b) * (hi - v) / (hi - lo);
    const grid = [-50, 0, 50].filter((v) => v > lo && v < hi).map((v) => `<line x1="${l}" x2="${w - r}" y1="${ys(v)}" y2="${ys(v)}" stroke="${v === 0 ? C.g5 : C.g2}" stroke-width="${v === 0 ? .7 : .6}" ${v === 0 ? 'stroke-dasharray="2 2"' : ""}/><text x="${l - 5}" y="${ys(v) + 3}" text-anchor="end" class="ax">${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v)}</text>`).join("");
    const path = `<path d="M ${H0.map((x, i) => `${xs(i).toFixed(1)} ${ys(x.S).toFixed(1)}`).join(" L ")}" fill="none" stroke="${C.ink}" stroke-width="1.4"/>`;
    const pts = H0.map((x, i) => `<circle cx="${xs(i)}" cy="${ys(x.S)}" r="${x.t === t0 ? 3.8 : 2.4}" fill="${C.ink}"/><text x="${xs(i)}" y="${ys(x.S) - 7}" text-anchor="middle" class="pv">${ESC.txt(x.S)}</text><text x="${xs(i)}" y="${h - 22}" text-anchor="middle" class="ax${x.t === t0 ? " on" : ""}">${E(x.t.slice(2))}${x.prov ? "*" : ""}</text><text x="${xs(i)}" y="${h - 12}" text-anchor="middle" class="ax">${ok(x.w) ? `${x.w}-${x.l}` : "–"}</text><text x="${xs(i)}" y="${h - 3}" text-anchor="middle" class="ax">${E(LC[x.liga] || ESC.ligaCorto(x.liga))}</text>`).join("");
    return `<svg class="ieq-ev" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="Evolución del nivel de la plantilla">${grid}${path}${pts}</svg>`;
  }
  // de dónde tira: reparto de tiros por zona, equipo frente a la media de la liga
  function zonasSVG(T, o = {}) {
    const Z = [["aro", "En el aro"], ["corta", "Corta distancia"], ["media", "Media distancia"], ["t3_esquina", "Triple de esquina"], ["t3_frontal", "Triple frontal"]];
    const tot = (x) => Z.reduce((a, [z]) => a + x[z][0], 0), te = tot(T.tiro), tl = tot(T.tiroL); if (!te || !tl) return "";
    const w = o.w || 330, rh = 30, lw = 104, rw = 70, bw = w - lw - rw, h = Z.length * rh + 4, max = Math.max(...Z.map(([z]) => Math.max(T.tiro[z][0] / te, T.tiroL[z][0] / tl))) * 1.05;
    const rows = Z.map(([z, n], i) => { const y = 2 + i * rh, pe = T.tiro[z][0] / te, pl = T.tiroL[z][0] / tl, a3 = /^t3/.test(z) ? 1.5 : 1, ae = T.tiro[z][0] ? a3 * T.tiro[z][1] / T.tiro[z][0] : null, al = T.tiroL[z][0] ? a3 * T.tiroL[z][1] / T.tiroL[z][0] : null, dA = ae != null && al != null ? 100 * (ae - al) : null;
      return `<text x="0" y="${y + 11}" class="nm">${n}</text><rect x="${lw}" y="${y + 3}" width="${(pe / max * bw).toFixed(1)}" height="9" fill="${C.ink}"/><rect x="${lw}" y="${y + 15}" width="${(pl / max * bw).toFixed(1)}" height="6" fill="${C.g4}"/><text x="${lw + pe / max * bw + 4}" y="${y + 11}" class="vv">${N(100 * pe, 0)} %</text><text x="${w}" y="${y + 11}" text-anchor="end" class="vv" fill="${dA == null || Math.abs(dA) < 1.5 ? C.ink : dA > 0 ? C.s700 : C.dn}">${dA == null ? "–" : `${SG0(dA, 0)} pp`}</text><text x="${w}" y="${y + 22}" text-anchor="end" class="ax">acierto</text>`; }).join("");
    return `<svg class="ieq-zn" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="Reparto de tiros por zona">${rows}</svg>`;
  }
  // puesto por nivel de plantilla frente a puesto por balance (pizarra)
  function puestosSVG(c, o = {}) {
    if (!c.rkPl || !c.rkW) return "";
    const w = o.w || 330, h = 92, n = Math.max(c.nPl, c.nW), X = (k) => 14 + (w - 28) * (k - 1) / Math.max(1, n - 1);
    const fila = (y, lab, k) => `<text x="0" y="${y - 12}" class="ax">${lab}</text><line x1="14" x2="${w - 14}" y1="${y}" y2="${y}" stroke="${C.g2}"/>${Array.from({ length: n }, (_, i) => `<circle cx="${X(i + 1)}" cy="${y}" r="2.2" fill="${C.g4}"/>`).join("")}<circle cx="${X(k)}" cy="${y}" r="6.5" fill="${C.ink}"/><text x="${X(k)}" y="${y + 18}" text-anchor="middle" class="vv">${ord(k)}</text>`;
    return `<svg class="ieq-pu" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="Puesto por nivel y por balance">${fila(22, "Por nivel de la plantilla", c.rkPl)}${fila(68, "Por balance", c.rkW)}<line x1="${X(c.rkPl)}" y1="28" x2="${X(c.rkW)}" y2="62" stroke="${C.g5}" stroke-dasharray="2 2"/><text x="14" y="${h}" class="ax">1.º</text><text x="${w - 14}" y="${h}" text-anchor="end" class="ax">${n}.º</text></svg>`;
  }
  const chipRol = (j) => j.rol ? `<span class="r3rol r-${j.rol.toLowerCase()}${j.rolEst ? " est" : ""}">${ROLN[j.rol]}</span>` : "–";
  const swE = (col) => col ? `<i class="r3sw" style="background:${col}"></i>` : "";
  // muestra del estilo con la serie corporativa (borde cuando el relleno es claro)
  const swEst = (k) => { if (!ok(k)) return ""; const e = estC(k), claro = e.s !== "#F3F4F0"; return `<i class="r3sw" style="background:${e.f};${claro ? `box-shadow:inset 0 0 0 1px ${e.s}` : ""}"></i>`; };
  const leyendaEst = (ks, pre) => { const eus = EUS(); return `<p class="ieq-ley est">${pre ? `<span class="pre">${E(pre)}</span>` : ""}${(ks || eus.map((_, k) => k)).filter((k) => eus[k]).map((k) => `<span>${swEst(k)}${E(eus[k].nombre)}</span>`).join("")}</p>`; };
  const pTxt = (p) => p == null ? "–" : `percentil ${Math.round(p)}`;
  const tono = (p, dir) => dir === 0 ? "neu" : p == null ? "" : p >= 65 ? "up" : p <= 35 ? "dn" : "";

  // ------------------------------------------------------------------------------------------- 2b. piezas v1.4
  // intervalo del 80 % de una media (aproximación normal): n observaciones, suma y suma de cuadrados
  function ic80(n, s, s2) {
    if (!ok(n) || n < 8 || !ok(s) || !ok(s2)) return null;
    const m = s / n, v = Math.max(0, (s2 - n * m * m) / (n - 1)), h = 1.2816 * Math.sqrt(v / n);
    return [m - h, m + h];
  }
  // barra al 100 % por categorías: equipo (gruesa) y media de su liga (fina) [{v, f, t, s}]
  function barra100(eq, lg, cats, o = {}) {
    const w = o.w || 690, lw = o.lw || 112, bw = w - lw - 4, h = 34;
    const seg = (vals, y, hh, conTxt) => { let x = lw; return vals.map((v, i) => { const ww = Math.max(0, v / 100 * bw), c0 = cats[i], r = `<rect x="${x.toFixed(1)}" y="${y}" width="${Math.max(0, ww - 0.8).toFixed(1)}" height="${hh}" fill="${c0.f}"${c0.s && c0.s !== C.paper ? ` stroke="${c0.s}" stroke-width=".6"` : ""}/>${conTxt && ww >= 30 ? `<text x="${(x + ww / 2).toFixed(1)}" y="${y + hh / 2 + 3}" text-anchor="middle" class="vv" style="fill:${c0.t}" fill="${c0.t}">${N(v, 0)} %</text>` : ""}`; x += ww; return r; }).join(""); };
    return `<svg class="ieq-b100" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="${E(o.aria || "")}"><text x="0" y="13" class="nm">${E(o.lab || "")}</text><text x="0" y="29" class="ax">media de su liga</text>${seg(eq, 1, 16, true)}${lg ? seg(lg, 23, 6, false) : ""}</svg>`;
  }
  // 02 · cómo está construida la plantilla: minutos por puesto, edad y estilo, frente a las plantillas de su liga
  function composicion(c) {
    const P = EVX && EVX.P, pl = P && P[c.r.k]; if (!pl || !Array.isArray(pl.j) || pl.j.length < 3) return "";
    const lgP = c.lg.map((x) => P[x.k]).filter((p) => p && Array.isArray(p.j) && p.j.length >= 3);
    const eus = EUS();
    const DIM = [["Puesto", (a) => ({ E: 0, A: 1, I: 2 })[a[1]], [{ n: "Exteriores", f: C.ink, t: C.paper }, { n: "Aleros", f: C.g5, t: C.paper }, { n: "Interiores", f: C.g3, t: C.ink }]],
      ["Edad", (a) => !ok(a[2]) ? null : a[2] <= 23 ? 0 : a[2] <= 27 ? 1 : a[2] <= 31 ? 2 : 3, [{ n: "23 años o menos", f: C.g2, t: C.ink, s: C.g5 }, { n: "24 a 27", f: C.g4, t: C.ink }, { n: "28 a 31", f: C.g6, t: C.paper }, { n: "32 o más", f: C.ink, t: C.paper }]],
      ["Estilo de juego", (a) => ok(a[5]) && eus[a[5]] ? a[5] : null, eus.map((e, k) => ({ n: e.nombre, ...estC(k) })), true]];
    const reparto = (js, f, n) => { const o = Array(n).fill(0); let T = 0; js.forEach((a) => { const k = f(a); if (k == null || !ok(a[3])) return; o[k] += a[3]; T += a[3]; }); return T ? o.map((v) => 100 * v / T) : null; };
    const mediaV = (arrs, n) => { const a = arrs.filter(Boolean); return a.length ? Array.from({ length: n }, (_, i) => a.reduce((s, x) => s + x[i], 0) / a.length) : null; };
    // el estilo sale del Atlas (estilo unificado de cada jugador, el mismo de las fichas): jugadores con 100 minutos o más
    // de cada club de su liga y temporada, en el formato de la plantilla ([, , , minutos, , estilo])
    const porClub = new Map(); JG.filter((j) => j.liga === c.l && j.temporada === c.t && (j.min || 0) >= 100 && ok(j.eu)).forEach((j) => { const a = porClub.get(j.clave) || []; a.push([j.nombre, j.pos3, j.edad, j.min, j.L, j.eu]); porClub.set(j.clave, a); });
    const estEq = c.at ? porClub.get(c.at.clave) || [] : [], estLg = [...porClub.values()].filter((a) => a.length >= 3);
    const filas = DIM.map(([lab, f, cats, atlas]) => ({ lab, cats, eq: reparto(atlas ? estEq : pl.j, f, cats.length), lg: mediaV((atlas ? estLg : lgP.map((p) => p.j)).map((js) => reparto(js, f, cats.length)), cats.length) })).filter((x) => x.eq);
    if (!filas.length) return "";
    const top5 = (js) => { const a = js.map((x) => x[3]).filter(ok).sort((p, q) => q - p), T = a.reduce((s, v) => s + v, 0); return T ? 100 * a.slice(0, 5).reduce((s, v) => s + v, 0) / T : null; };
    const t5 = top5(pl.j), t5L = media(lgP.map((p) => ({ v: top5(p.j) })), "v"), edL = media(lgP.map((p) => ({ v: p.edad })), "v"), nL = media(lgP.map((p) => ({ v: p.n })), "v");
    // lo que más la distingue de las plantillas de su liga (6 puntos o más)
    const frases = filas.map((d) => { if (!d.lg) return null; let k = 0; d.eq.forEach((v, i) => { if (Math.abs(v - d.lg[i]) > Math.abs(d.eq[k] - d.lg[k])) k = i; }); const dd = d.eq[k] - d.lg[k]; return Math.abs(dd) >= 6 ? `${d.lab === "Estilo de juego" ? `estilo ${d.cats[k].n}` : d.cats[k].n.toLowerCase()}: ${dd > 0 ? "más" : "menos"} minutos que la plantilla media de su liga (${N(d.eq[k], 0)} % frente a ${N(d.lg[k], 0)} %)` : null; }).filter(Boolean);
    const kp = `<div class="r3mini ieq-comp"><div><span>Edad media</span><b>${ok(pl.edad) ? N(pl.edad, 1) : "–"}</b><small>${ok(edL) ? `liga ${N(edL, 1)} · ponderada por minutos` : "ponderada por minutos"}</small></div><div><span>Jugadores con 100'+</span><b>${N(pl.n, 0)}</b><small>${ok(nL) ? `liga ${N(nL, 1)}` : ""}</small></div><div><span>Minutos de sus 5 más usados</span><b>${t5 != null ? PC(t5, 0) : "–"}</b><small>${ok(t5L) ? `liga ${PC(t5L, 0)} · más alto, plantilla más corta` : ""}</small></div></div>`;
    const barrasH = filas.map((d) => `${barra100(d.eq, d.lg, d.cats, { lab: d.lab, aria: `Minutos por ${d.lab.toLowerCase()}` })}<p class="ieq-ley">${d.cats.map((x, i) => d.eq[i] > 0.4 || (d.lg && d.lg[i] > 0.4) ? `<span><i style="background:${x.f};${x.s && x.s !== C.paper ? `box-shadow:inset 0 0 0 1px ${x.s}` : ""}"></i>${E(x.n)}</span>` : "").join("")}</p>`).join("");
    return `<div class="r3blk ieq-compb"><h3>Cómo está construida la plantilla</h3>${kp}${barrasH}
      <p class="r3p ieq-compt">${frases.length ? `Lo que más la distingue: ${E(frases.join("; "))}.` : "Su reparto de minutos por puesto, edad y estilo se parece al de la plantilla media de su liga."}</p>
      <p class="r3n">Reparto de los minutos de toda la plantilla (jugadores con 100 minutos o más) en ${E(c.ligaNom)} ${E(c.t)}; el estilo, el de cada jugador en el Atlas. Barra gruesa: el equipo; barra fina: la media de las plantillas de su liga.</p></div>`;
  }

  // 04 (segunda hoja) · tiempos muertos: cuándo los pide, tras qué parcial y qué pasa después, frente a su liga
  function derTM(e) {
    const t = e.tiempos_muertos || {}, d = e.defensa || {};
    const ppp = d.of_pos ? d.of_pts / d.of_pos : null, ato = t.ato_n ? t.ato_pts / t.ato_n : null;
    return { n: t.n || 0, gp: t.partidos_con_registro || 0, pp: t.por_partido, q: t.por_cuarto || [], fin: t.n ? 100 * t.ultimos_2min / t.n : null,
      racha: t.n ? 100 * t.tras_racha / t.n : null, corta: t.racha_con_ventana ? 100 * t.racha_cortada / t.racha_con_ventana : null, nr: t.racha_con_ventana || 0,
      pre: t.parcial_antes_medio, post: t.parcial_despues_medio, rpost: t.racha_parcial_despues_medio, ppp, ato, atoD: ato != null && ppp != null ? ato - ppp : null,
      atoN: t.ato_n || 0, icPost: ic80(t.post_n, t.post_s, t.post_s2), icAto: ic80(t.ato_n, t.ato_pts, t.ato_pts2), ventaja: t.n ? 100 * t.con_ventaja / t.n : null };
  }
  function cuartosSVG(yo, lg, o = {}) {
    const lab = ["1.º", "2.º", "3.º", "4.º", "Prórroga"], tot = (q) => q.reduce((a, b) => a + b, 0);
    const pe = yo.q.map((v) => tot(yo.q) ? 100 * v / tot(yo.q) : 0), pl = lab.map((_, i) => media(lg.map((x) => ({ v: tot(x.q) ? 100 * x.q[i] / tot(x.q) : null })), "v") || 0);
    const w = o.w || 330, rh = 26, lw = 74, bw = w - lw - 44, h = lab.length * rh + 4, mx = Math.max(10, ...pe, ...pl) * 1.05;
    return `<svg class="ieq-zn" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="Tiempos muertos por cuarto">${lab.map((n, i) => { const y = 2 + i * rh; return `<text x="0" y="${y + 11}" class="nm">${n === "Prórroga" ? n : `${n} cuarto`}</text><rect x="${lw}" y="${y + 3}" width="${(pe[i] / mx * bw).toFixed(1)}" height="9" fill="${C.ink}"/><rect x="${lw}" y="${y + 15}" width="${(pl[i] / mx * bw).toFixed(1)}" height="5" fill="${C.g4}"/><text x="${w}" y="${y + 11}" text-anchor="end" class="vv">${N(pe[i], 0)} %</text><text x="${w}" y="${y + 21}" text-anchor="end" class="ax">liga ${N(pl[i], 0)} %</text>`; }).join("")}</svg>`;
  }
  // parcial de los 2 minutos antes y después del tiempo muerto: equipo y media de su liga, sobre un eje en puntos
  function antesDespuesSVG(filas, o = {}) {
    const w = o.w || 330, rh = 40, lw = 118, bw = w - lw - 12, h = filas.length * rh + 22;
    const vs = filas.flatMap((f) => [f.pre, f.post].filter(ok)), lo = Math.min(-8, Math.floor(Math.min(...vs) - 1)), hi = Math.max(4, Math.ceil(Math.max(...vs) + 1));
    const X = (v) => lw + (v - lo) / (hi - lo) * bw;
    const ax = Array.from({ length: hi - lo + 1 }, (_, i) => lo + i).filter((v) => v % 2 === 0).map((v) => `<line x1="${X(v)}" x2="${X(v)}" y1="4" y2="${h - 16}" stroke="${v === 0 ? C.g5 : C.g2}" stroke-width="${v === 0 ? .8 : .5}"/><text x="${X(v)}" y="${h - 5}" text-anchor="middle" class="ax">${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v)}</text>`).join("");
    const rows = filas.map((f, i) => { const y = 10 + i * rh + 8; if (!ok(f.pre) || !ok(f.post)) return ""; const x0 = X(f.pre), x1 = X(f.post), col = f.yo ? C.ink : C.g5;
      return `<text x="0" y="${y + 3}" class="nm">${E(f.lab)}</text>${f.ic ? `<rect x="${X(f.ic[0]).toFixed(1)}" y="${y - 5}" width="${Math.max(1, X(f.ic[1]) - X(f.ic[0])).toFixed(1)}" height="10" fill="rgba(15, 46, 37, .14)"/>` : ""}<line x1="${x0.toFixed(1)}" x2="${x1.toFixed(1)}" y1="${y}" y2="${y}" stroke="${col}" stroke-width="1.6"/><circle cx="${x0.toFixed(1)}" cy="${y}" r="3.6" fill="${C.paper}" stroke="${col}" stroke-width="1.4"/><circle cx="${x1.toFixed(1)}" cy="${y}" r="4.6" fill="${col}"/><text x="${x0.toFixed(1)}" y="${y - 8}" text-anchor="middle" class="ax">${SG(f.pre, 1)}</text><text x="${x1.toFixed(1)}" y="${y + 16}" text-anchor="middle" class="vv">${SG(f.post, 1)}</text>`; }).join("");
    return `<svg class="ieq-ad" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="Parcial antes y después del tiempo muerto">${ax}${rows}</svg><p class="ieq-ley"><span><i style="background:${C.paper};box-shadow:inset 0 0 0 1.4px ${C.ink}"></i>2 minutos antes</span><span><i style="background:${C.ink}"></i>2 minutos después</span><span><i style="background:rgba(15, 46, 37, .14)"></i>rango del 80 % de «después»</span></p>`;
  }
  function paginaTiempos(c) {
    const X = c.X, f = c.s.fase; if (!X || !X.equipos || !c.XE || !c.XE.tiempos_muertos || !(c.XE.tiempos_muertos.n >= 5)) return "";
    const R = Object.entries(X.equipos).map(([tid, e]) => e[f] && e[f].tiempos_muertos && e[f].tiempos_muertos.n >= 5 ? { tid, ...derTM(e[f]) } : null).filter(Boolean);
    const yo = R.find((x) => x.tid === c.s.eq); if (!yo || R.length < 4) return "";
    const mL = (k) => media(R, k), P = (k, dir) => pctL(R, k, yo[k], dir);
    const pPost = P("post", 1), pAto = P("atoD", 1), pCorta = P("corta", 1);
    const qMax = yo.q.indexOf(Math.max(...yo.q)), qTxt = ["el primer cuarto", "el segundo cuarto", "el tercer cuarto", "el último cuarto", "las prórrogas"][qMax];
    const juicio = (p) => p == null ? "" : p >= 65 ? "por encima de su liga" : p <= 35 ? "por debajo de su liga" : "en la media de su liga";
    const lead = `Pide <b>${N(yo.pp, 1)} tiempos muertos por partido</b> (media de su liga ${N(mL("pp"), 1)}), sobre todo en ${qTxt}. El ${N(yo.racha, 0)} % llega tras un parcial en contra de 6 puntos o más. En los 2 minutos siguientes su parcial medio es ${SG(yo.post, 1)} (liga ${SG(mL("post"), 1)}): ${juicio(pPost)}.`;
    const icTxt = (ic, d = 1, sg = true) => ic ? `[${sg ? SG(ic[0], d) : N(ic[0], d)} – ${sg ? SG(ic[1], d) : N(ic[1], d)}]` : "";
    const icA = yo.icAto && yo.ppp != null ? [yo.icAto[0] - yo.ppp, yo.icAto[1] - yo.ppp] : null;
    const kp = `<div class="r3kp big ieq-tmk"><div><span>Por partido</span><b>${N(yo.pp, 1)}</b><small>liga ${N(mL("pp"), 1)} · ${N(yo.n, 0)} en ${N(yo.gp, 0)} partidos</small></div>
      <div><span>Tras un parcial en contra</span><b>${PC(yo.racha, 0)}</b><small>de 6 o más en 2 minutos · liga ${PC(mL("racha"), 0)}</small></div>
      <div class="idx"><span>Parcial 2 minutos después</span><b class="${tono(pPost, 1)}">${SG(yo.post, 1)}</b><small>${icTxt(yo.icPost)} · ${pTxt(pPost)}</small></div>
      <div><span>Primera posesión después</span><b class="${tono(pAto, 1)}">${N(yo.ato, 2)}</b><small>puntos (${SG(yo.atoD, 2)} frente a su media) ${icTxt(icA, 2)}</small></div></div>`;
    const tiraK = (k, lab, q, izq, der, txt, sub, neu, dir = 1) => { const vals = R.filter((x) => ok(x[k])).map((x) => [x[k], x === yo]); if (vals.length < 4 || !ok(yo[k])) return ""; const p = pctL(R, k, yo[k], dir);
      return `<div class="ieq-tr"><div><b>${E(lab)}</b><small>${E(q)}</small></div>${tira(vals, { dir, p, neu, w: 300, izq, der, aria: lab })}<div class="ieq-trv"><b class="${neu ? "neu" : tono(p, 1)}">${txt}</b><small>${E(sub)}</small></div></div>`; };
    const tiras = [tiraK("pp", "Cuántos pide", "Por partido.", "pocos", "muchos", N(yo.pp, 1), `media ${N(mL("pp"), 1)}`, true),
      tiraK("fin", "Los guarda para el final", "En los 2 últimos minutos del partido.", "pocos", "muchos", PC(yo.fin, 0), `media ${PC(mL("fin"), 0)}`, true),
      tiraK("racha", "Reacciona a las rachas", "Tras un parcial en contra de 6 o más.", "pocas veces", "casi siempre", PC(yo.racha, 0), `media ${PC(mL("racha"), 0)}`, true),
      tiraK("post", "Parcial después", "Puntos propios menos del rival, 2 minutos.", "peor", "mejor", SG(yo.post, 1), `${ord(rangoL(R, "post", yo.post, 1))} de ${R.length}`, false),
      tiraK("corta", "Rachas cortadas", "Tras una racha, no pierde los 2 minutos siguientes.", "menos", "más", PC(yo.corta, 0), `${N(yo.nr, 0)} rachas · media ${PC(mL("corta"), 0)}`, false),
      tiraK("atoD", "Jugada tras tiempo muerto", "Primera posesión frente a su media.", "peor", "mejor", SG(yo.atoD, 2), `${N(yo.atoN, 0)} posesiones`, false)].join("");
    const filasAD = [{ lab: "Sus tiempos muertos", pre: yo.pre, post: yo.post, ic: yo.icPost, yo: true }, { lab: "Media de su liga", pre: mL("pre"), post: mL("post") }];
    const cob = ok(c.r.gp) && yo.gp < c.r.gp ? ` Jugada a jugada de ${N(yo.gp, 0)} de sus ${N(c.r.gp, 0)} partidos.` : "";
    return `${ceja(0, "", "Huella del entrenador", lead)}
      <h3 class="ieq-h3s">Tiempos muertos: cuándo los pide y qué pasa después</h3>
      ${kp}
      <div class="r3cols c2"><div class="r3blk"><h3>Cuándo los pide</h3>${cuartosSVG(yo, R, { w: 330 })}<p class="r3n">Reparto de sus tiempos muertos por cuarto (negro) frente a la media de su liga (gris). En los 2 últimos minutos: ${PC(yo.fin, 0)} (liga ${PC(mL("fin"), 0)}). Con ventaja en el marcador: ${PC(yo.ventaja, 0)}.</p></div>
        <div class="r3blk"><h3>El parcial, antes y después</h3>${antesDespuesSVG(filasAD, { w: 330 })}<p class="r3n">Puntos propios menos los del rival en los 2 minutos anteriores y en los 2 siguientes al tiempo muerto. Tras una racha en contra, el parcial siguiente medio es ${SG(yo.rpost, 1)}.</p></div></div>
      <div class="r3blk"><h3>Frente a los entrenadores de su liga</h3>${tiras}</div>
      <p class="r3p ieq-lim"><b>Cómo leerlo.</b> Tras una racha, el marcador tiende a equilibrarse con o sin tiempo muerto: es la vuelta a la media. Por eso cada cifra se compara con los demás equipos de ${E(c.ligaNom)}, que también paran después de sus rachas. Lo que distingue a un entrenador es quedar por encima o por debajo de ellos. Asociación, no causa: con estas muestras, una diferencia de un punto en el parcial está dentro del ruido.</p>
      <p class="r3n">Tiempos muertos pedidos por el equipo (no los oficiales ni los de televisión) en ${E(FNOM[c.s.fase])}, del jugada a jugada.${cob} «Primera posesión»: puntos de su primera posesión que empieza en los 30 segundos siguientes. Rangos del 80 % para la media.</p>`;
  }

  // 07 · stops: posesiones del rival que acaban sin puntos y cómo se consiguen, frente a su liga
  function bloqueStops(c) {
    const X = c.X, f = c.s.fase, d0 = c.XE && c.XE.defensa; if (!X || !d0 || !(d0.pos >= 50)) return "";
    const der = (tid, x) => ({ tid, pos: x.pos, sp: 100 * x.stops / x.pos, ppp: x.pts / x.pos, rob: 100 * (x.stop_robo || 0) / x.pos, per: 100 * (x.stop_perdida || 0) / x.pos,
      tap: 100 * (x.stop_tapon || 0) / x.pos, fal: 100 * (x.stop_fallo || 0) / x.pos, orb: 100 * (x.pos_oreb || 0) / x.pos, sor: x.pos_oreb ? 100 * (x.stop_tras_oreb || 0) / x.pos_oreb : null });
    const R = Object.entries(X.equipos).map(([tid, e]) => e[f] && e[f].defensa && e[f].defensa.pos >= 50 ? der(tid, e[f].defensa) : null).filter(Boolean);
    const yo = R.find((x) => x.tid === c.s.eq); if (!yo || R.length < 4) return "";
    const mL = (k) => media(R, k), pSp = pctL(R, "sp", yo.sp, 1), rk = rangoL(R, "sp", yo.sp, 1);
    const h = 1.2816 * Math.sqrt(yo.sp * (100 - yo.sp) / yo.pos), partidos = (c.XE.partidos || c.r.gp || 1);
    const posPP = yo.pos / partidos, dStops = (yo.sp - mL("sp")) / 100 * posPP;
    const CAT = [["rob", "Robo", C.ink, C.paper], ["per", "Otra pérdida", C.g6, C.paper], ["tap", "Fallo con tapón", C.g4, C.ink], ["fal", "Fallo forzado", C.g2, C.ink, C.g5]];
    const cats = [...CAT.map(([, n, fi, t, s]) => ({ n, f: fi, t, s })), { n: "Anota", f: C.paper, t: C.ink, s: C.g4 }];
    const eqV = [...CAT.map(([k]) => yo[k]), 100 - yo.sp], lgV = [...CAT.map(([k]) => mL(k)), 100 - mL("sp")];
    // cada vía de stop, con la faceta de la defensa que la explica
    const LIGA = { rob: ["stl", "robos"], per: ["otov", "pérdidas que fuerza"], tap: ["blk", "tapones"], fal: ["oefg", "acierto que concede"] };
    const dif = CAT.map(([k, n]) => ({ k, n: n.toLowerCase(), d: yo[k] - mL(k), v: yo[k], m: mL(k) })).sort((a, b) => b.d - a.d);
    const mas = dif[0].d >= 0.8 ? dif[0] : null, menos = dif[dif.length - 1].d <= -0.8 ? dif[dif.length - 1] : null;
    const fac = (x) => { const [mk, mn] = LIGA[x.k], m = c.met[mk]; return m && m.p != null ? `; en ${mn}, ${pTxt(m.p)} de su liga` : ""; };
    const via = (x) => `<b>${E(x.n)}</b> (${PC(x.v, 1)} de las posesiones rivales frente a ${PC(x.m, 1)}${fac(x)})`;
    const porque = `${mas && menos ? `Consigue más stops que la media por ${via(mas)} y menos por ${via(menos)}.` : mas ? `Consigue más stops que la media por ${via(mas)}; el resto de vías está en la media de su liga.` : menos ? `Ninguna vía de stop supera a la media de su liga, y se queda por debajo en ${via(menos)}.` : "Sus vías de stop están en la media de su liga."} ${Math.abs(dStops) >= 0.3 ? `Su diferencia con la media equivale a ${N(Math.abs(dStops), 1)} posesiones rivales ${dStops > 0 ? "más" : "menos"} sin puntos por partido.` : "En posesiones vacías por partido, está en la media de su liga."}`;
    return `<div class="r3blk ieq-stops"><h3>Stops: posesiones del rival sin puntos</h3>
      <div class="r3mini ieq-comp"><div><span>% de stops</span><b class="${tono(pSp, 1)}">${PC(yo.sp, 1)}</b><small>[${N(yo.sp - h, 1)} – ${N(yo.sp + h, 1)}] · ${ord(rk)} de ${R.length} · liga ${PC(mL("sp"), 1)}</small></div>
        <div><span>Puntos por posesión rival</span><b>${N(yo.ppp, 2)}</b><small>liga ${N(mL("ppp"), 2)} · menos es mejor</small></div>
        <div><span>Segundas oportunidades</span><b>${PC(yo.orb, 1)}</b><small>posesiones rivales con rebote ofensivo · ${yo.sor != null ? `${PC(yo.sor, 0)} acaban en stop` : ""}</small></div></div>
      ${barra100(eqV, lgV, cats, { lab: "Cómo acaban", aria: "Cómo acaban las posesiones del rival" })}
      <p class="ieq-ley">${cats.map((x) => `<span><i style="background:${x.f};${x.s ? `box-shadow:inset 0 0 0 1px ${x.s}` : ""}"></i>${E(x.n)}</span>`).join("")}</p>
      <p class="r3p ieq-compt">${porque}</p>
      <p class="r3n">Stop: posesión del rival que acaba sin puntos, contada en el jugada a jugada (${N(yo.pos, 0)} posesiones rivales). Robo: pérdida con robo de su defensa; fallo con tapón: posesión sin puntos con un tapón suyo; fallo forzado: el resto de fallos sin puntos. Rango del 80 % para el % de stops.</p></div>`;
  }

  // ------------------------------------------------------------------------------------------- 3. hojas
  function hoja(cuerpo, o) {
    if (o.portada) return `<article class="ifsheet r3 cover${o.back ? " back" : ""}"><div class="ifbody">${cuerpo}</div></article>`;
    return `<article class="ifsheet r3 ieq${o.cls ? " " + o.cls : ""}"><header class="r3head"><span class="r3label">KERNO ANALYTICS — INFORME DE EQUIPO · CONFIDENCIAL</span><span class="r3label">${E(o.extra || "")}</span><span class="r3hsec r3label">${o.anexo ? "ANEXO" : String(o.num).padStart(2, "0")} · ${E(o.sec.split(",")[0].toUpperCase())}</span></header>
      <div class="ifbody r3body">${cuerpo}</div><footer class="r3foot">${ifEscala(o.n, o.N)}<span>${E(o.fecha)}</span><span>${String(o.n).padStart(2, "0")} / ${String(o.N).padStart(2, "0")}</span></footer></article>`;
  }
  // el número de sección se pone al final, según el orden real de las páginas (hay secciones que dependen de los datos)
  const ceja = (num, nombre, h2, lead) => `<div class="r3secw"><div class="r3sec ink"><div><span class="r3ceja">Sección #N#${nombre ? ` · ${E(nombre)}` : ""}</span><h2>${h2}</h2></div><b class="r3num">#N#</b></div>${lead ? `<p class="r3lead">${lead}</p>` : ""}</div>`;
  function barraPR(v, lo, hi, o = {}) { // el mismo dibujo de «Cómo leer las cifras» de la lectura de fichaje
    const w = o.w || 150, x = (p) => 4 + (w - 8) * p / 100;
    return `<svg class="r3pr" viewBox="0 0 ${w} 14" width="${w}" height="14" aria-hidden="true"><line x1="4" x2="${w - 4}" y1="7" y2="7" class="tr"/>${o.ref != null ? `<line x1="${x(o.ref)}" x2="${x(o.ref)}" y1="2" y2="12" class="rf"/>` : ""}${lo != null && hi != null ? `<rect x="${x(lo)}" y="3" width="${x(hi) - x(lo)}" height="8" class="bd"/>` : ""}<circle cx="${x(v)}" cy="7" r="3.6" class="pt ${o.cls || ""}"/></svg>`;
  }

  function paginas(c) {
    const V = "B", r = c.r, t = c.t, nomE = c.nombre, T = c.T, fecha = c.fecha, pags = [];
    const ref = `READ ${new Date().toISOString().slice(2, 10).replace(/-/g, "")}-${(nomE.match(/\p{L}+/gu) || ["X"]).map((w) => w[0]).join("").slice(0, 3).toUpperCase()}`;
    const extra = `${ref} · ${c.para}`.toUpperCase().slice(0, 46), entAct = c.ent.length ? c.ent[c.ent.length - 1] : null;
    const balTxt = c.bal ? `${c.bal.w}-${c.bal.l}` : "–", pctW = c.bal && c.bal.w + c.bal.l ? 100 * c.bal.w / (c.bal.w + c.bal.l) : null;
    const balNota = c.bal && c.bal.src === "entrenadores" ? " La fuente oficial no publica el balance por fases: es el de sus entrenadores, que puede incluir playoffs." : c.bal && c.bal.src === "total" ? " Balance de toda la temporada (la fuente no lo separa por fases)." : "";
    const Snet = SV(r.net, c.vNet);
    const v4 = c.v40 && c.v40.eq && ok(c.v40.eq.net) ? c.v40.eq : null;       // v4.0 · Net proyectado de la plantilla
    (c.jugTodos || c.jug || []).forEach((j) => { j.corto = j.j != null ? snJ(c, j.j) : j.ape; });
    const okI = (i) => !c.okI || c.okI.has(i);

    // 0 · portada (la de la lectura de fichaje, con el equipo)
    const ficha = [["Competición", c.ligaNom], ["Temporada", `${t}${c.prov ? " (en curso)" : ""}`], ["Entrenador", entAct ? entAct.n + (c.ent.length > 1 ? ` (+${c.ent.length - 1})` : "") : "–"], ["Balance", c.bal ? `${balTxt} · ${N(pctW, 0)} %` : "–"]];
    pags.push({ portada: true, html: `<img class="cvestela" src="${INF_LOGO.est}" alt="" aria-hidden="true"><div class="cvtop"><img src="${INF_LOGO.hn}" alt="KERNO Analytics" class="cvlogo"></div>
      <div class="cvmid"><span class="cvk">Informe de equipo · ${E(t)} · Confidencial · ${ref}</span><h1 class="${nomE.length > 26 ? "xl" : nomE.length > 16 ? "l" : ""}">${E(nomE)}</h1>
        <p class="cvdat">${E(c.ligaNom)} · temporada ${E(t)} · ${E(FNOM[c.s.fase])}<br>Estado del equipo frente a su liga: rendimiento, rotación, quintetos y conexiones</p>
        <dl class="cvfacts">${ficha.map(([a, v]) => `<div><dt>${a}</dt><dd>${E(v)}</dd></div>`).join("")}</dl></div>
      <ol class="cvidx">#INDICE#</ol>
      <div class="cvbot"><span>Preparado para ${E(c.para)}</span><span>${E(fecha)}</span></div>` });

    // 1 · Kerno Analytics (idéntica a la lectura de fichaje; el percentil se define frente a los equipos de su liga)
    pags.push({ sec: "Una lectura en contexto", html: `${ceja(1, "", "Una lectura en contexto", "Sabrás qué jugador encaja, por qué y con cuánta seguridad.")}
      <div class="r3cols"><div><p class="r3p">Kerno Analytics es un socio independiente de inteligencia de talento para el deporte de élite, empezando por el baloncesto. Combinamos modelos predictivos con conocimiento profundo del juego para mostrar a los clubes cómo encaja un jugador en su sistema, en qué es probable que se convierta y con cuánta seguridad lo afirmamos.</p>
        <p class="r3p">Trabajamos solo para el lado del club y con confidencialidad por defecto: esta lectura es suya. Un jugador no es bueno en abstracto; es bueno para un sistema, un rol y unos compañeros. Por eso no ordenamos por fama ni por estadística total, sino por encaje.</p></div>
        <div class="r3q"><span class="r3lab">Las preguntas de cada lectura</span>
          <dl><div><dt>Encaje</dt><dd>¿Cómo funciona en este sistema, con este rol y estos compañeros?</dd></div><div><dt>Trayectoria</dt><dd>¿De dónde viene y qué ha sostenido temporada a temporada?</dd></div><div><dt>Riesgo</dt><dd>¿Qué puede fallar y qué nos haría cambiar de opinión?</dd></div><div><dt>Valor</dt><dd>Relación entre lo que aporta y lo que cuesta. <em>Fuera de esta lectura: requiere los datos económicos del club.</em></dd></div></dl></div></div>
      <div class="r3steps"><span class="r3lab">Cómo hacemos la lectura</span><ol>
        <li><b>Vemos todos sus partidos</b><span>Actas oficiales y jugada a jugada de trece competiciones. Como el ojeador que no se queda con un solo partido: buscamos lo que se repite.</span></li>
        <li><b>Lo medimos en su propia pista</b><span>Una canasta en una liga no vale lo mismo que en otra. Por eso un equipo se mide con la vara de su liga, frente a los rivales que de verdad tiene.</span></li>
        <li><b>Lo ponemos en tu vestuario</b><span>Un tirador rinde distinto con un base que penetra al lado. Simulamos su rol, sus minutos, sus compañeros y el estilo del club para leer cómo jugaría aquí.</span></li>
        <li><b>Decimos cuánto sabemos</b><span>Cada cifra va con su margen. Si un dato descansa en pocos minutos o en un salto de liga grande, lo decimos. Una recomendación sin su incertidumbre es solo una opinión con decimales.</span></li></ol></div>
      <div class="r3read"><span class="r3lab">Cómo leer las cifras de esta lectura</span><div>
        <div><b>Punto y rango</b>${barraPR(62, 48, 74, { ref: 50, w: 120 })}<span>El punto es lo más probable; la franja, entre dónde se moverá. Cuanto más ancha, menos seguros estamos.</span></div>
        <div><b>Percentil</b><p class="r3big">80</p><span>Supera al 80 % de los equipos de su liga; 50 es el mediano. Cuando la cifra mejora al bajar (puntos que encaja, pérdidas), el percentil ya lo tiene en cuenta.</span></div>
        <div><b>Escala ±100</b><p class="r3big">0</p><span>La media de su liga. Positivo, por encima; negativo, por debajo. Se usa para nivel, impacto y química.</span></div>
        <div><b>Colores</b><p class="r3cols3"><i style="background:#2B6FBF"></i>mejor<i style="background:#D35C2A"></i>peor<i style="background:#6550CC"></i>rasgo de estilo</p><span>El violeta no es bueno ni malo: describe cómo juega (cuánto tira de tres, cuánto usa el balón).</span></div></div></div>
      <div class="r3vals"><span class="r3lab">Lo que guía cada lectura</span><div>
        <div><b>Contexto antes que promedios</b><span>Un jugador no es bueno en abstracto. Es bueno para un sistema, un rol y un presupuesto.</span></div>
        <div><b>Franqueza calibrada</b><span>Decimos lo que sabemos y cuánto lo sabemos. Cada recomendación incluye su rango y lo que nos haría cambiar de opinión.</span></div>
        <div><b>Discreción por diseño</b><span>Las listas de un club son suyas. Confidencialidad por defecto en procesos, datos y comunicación.</span></div></div></div>
      <div class="r3call callout"><span class="r3tag">Basketball judgment, model rigor</span><p>Este análisis no sustituye en ningún caso el scouting en pista y humano, solo lo complementa con rigor matemático y científico.</p></div>` });

    // 02 · identidad y plantilla (dos hojas: el equipo y sus jugadores)
    const S2 = "Identidad y plantilla";
    const verbo = c.prov ? "lleva" : "cerró";
    const lead2 = `${E(nomE)} ${verbo} ${E(FNOM[c.s.fase])} con <b>${balTxt}</b>${pctW != null ? ` (${N(pctW, 0)} % de victorias${c.rkW ? `, ${ord(c.rkW)} de ${c.nW}` : ""})` : ""} en ${E(c.ligaNom)}.${c.v40 && c.v40.eq && ok(c.v40.eq.net) ? ` Su plantilla proyecta un Net de <b>${SG0(c.v40.eq.net, 1)}</b> frente a la media de la liga (${ordA(c.v40.eq.puesto)} de ${c.v40.eq.n}), rango 80 % ${SG0(c.v40.eq.lo80, 1)} a ${SG0(c.v40.eq.hi80, 1)}.` : ` Su plantilla está en <b>${c.SL != null ? ESC.txt(c.SL) : "–"}</b> frente a las de su liga${c.rkPl ? `: la ${ordA(c.rkPl)} de ${c.nPl} por nivel` : ""}.`}`;
    const eu = c.eu, fu = c.fuertes[0], de = c.debiles[0];
    const hero = `<div class="r3inkhero"><span class="r3tag">Su equipo en una mirada</span>
        ${eu ? `<div class="r3inkheroE"><div><span>Estilo de juego</span><b>${swEst(eu.k)}${E(eu.etiqueta)}</b><small>${ok(eu.p) ? `claridad ${Math.round(100 * eu.p)} de 100` : ""}${c.club && ok(c.club.rob) ? ` · robustez ${Math.round(100 * c.club.rob)} de 100` : ""}</small></div><p>${E(eu.equipo || eu.definicion || "")}</p></div>` : ""}
        <div class="r3inkheroK">${v4 ? `<div class="anc"><span>Net proyectado · v4.0</span><b>${SG0(v4.net, 1)}</b><small>por 100 posesiones frente a la liga · ${ord(v4.puesto)} de ${v4.n} · rango 80 %: ${SG0(v4.lo80, 1)} a ${SG0(v4.hi80, 1)}${CONFK("net_equipo")}</small></div>` : `<div><span>Nivel de la plantilla</span><b class="${ESC.cls(c.SL)}">${c.SL != null ? ESC.txt(c.SL) : "–"}</b><small>${c.pPl != null ? `${pTxt(c.pPl)} entre las plantillas de su liga` : "escala ±100 · 0 = plantilla media de su liga"}</small></div>`}
          <div><span>Diferencia de puntos</span><b class="${ESC.cls(Snet)}">${Snet != null ? ESC.txt(Snet) : "–"}</b><small>${ok(r.net) ? `${SG(r.net, 1)} por 100 posesiones · ${ord(c.rkN)} de ${c.n}` : ""}</small></div>
          <div><span>Punto fuerte</span><b class="w">${fu ? E(fu.nm) : "–"}</b><small>${fu ? `${pTxt(fu.p)} en su liga` : "ninguna faceta destaca con claridad"}</small></div>
          <div><span>A mejorar</span><b class="w">${de ? E(de.nm) : "–"}</b><small>${de ? `${pTxt(de.p)} en su liga` : "ninguna faceta queda claramente atrás"}</small></div></div></div>`;
    const tiles = v4 ? [["Net proyectado · v4.0", SG0(v4.net, 1), `${ord(v4.puesto)} de ${v4.n} por plantilla · rango 80 %: ${SG0(v4.lo80, 1)} a ${SG0(v4.hi80, 1)}${CONFK("net_equipo")}`], ["Balance", balTxt, pctW != null ? `${N(pctW, 0)} % de victorias${c.rkW ? ` · ${ord(c.rkW)} de ${c.nW}` : ""}` : ""], ["Nivel de la plantilla", c.SL != null ? ESC.txt(c.SL) : "–", c.rkPl ? `${ord(c.rkPl)} de ${c.nPl} en su liga · escala ±100` : "escala ±100"], ["Partidos", N(r.gp, 0), `${FNOM[c.s.fase]} · edad media ${c.pl && ok(c.pl.edad) ? N(c.pl.edad, 1) : "–"}`]]
      : [["Balance", balTxt, pctW != null ? `${N(pctW, 0)} % de victorias${c.rkW ? ` · ${ord(c.rkW)} de ${c.nW}` : ""}` : ""], ["Nivel de la plantilla", c.SL != null ? ESC.txt(c.SL) : "–", c.rkPl ? `${ord(c.rkPl)} de ${c.nPl} en su liga` : ""], ["Partidos", N(r.gp, 0), FNOM[c.s.fase]], ["Edad media", c.pl && ok(c.pl.edad) ? N(c.pl.edad, 1) : "–", "ponderada por minutos"]];
    pags.push({ sec: S2, html: `${ceja(2, "", S2, lead2)}
      <div class="ieq-tiles${v4 ? " v40" : ""}">${tiles.map(([a, b, s], i) => `<div class="${i === 0 ? "idx" : ""}"><span>${a}</span><b>${E(b)}</b><small>${E(s)}</small></div>`).join("")}</div>
      ${hero}
      <div class="r3blk"><h3>Cuerpo técnico</h3>${pizarraEnt(c)}</div>
      <div class="r3blk"><h3>Evolución del club, temporada a temporada</h3>${evolSVG(c.hist, t, { w: 690, h: 150 })}<p class="r3n">Nivel de la plantilla frente a las de su liga ese año (escala ±100, 0 = plantilla media); debajo, su balance y su liga.${c.hist.some((x) => x.prov) ? " *Temporada en curso." : ""}</p></div>` });
    // la plantilla, jugador a jugador (antes, sección «Jugadores»), y cómo está construida
    const jsT = (c.jug || []).filter((j) => (j.mpg == null || j.mpg >= 0.5) && (j.min == null || j.min > 0)).slice(0, 14);
    const lead9 = (() => { const ra = jsT.filter((j) => j.Srapm != null && (j.min || 0) >= Math.max(300, c.minMin || 0)).sort((a, b) => b.Srapm - a.Srapm); return ra.length ? `${c.minMin > 300 ? `Con ${c.minMin} minutos o más` : "Con más de 300 minutos"}, el jugador con más impacto en pista es <b>${E(ra[0].nombre)}</b> (${ESC.txt(ra[0].Srapm)} en escala ±100)${ra.length > 1 ? ` y el que menos, ${E(ra[ra.length - 1].nombre)} (${ESC.txt(ra[ra.length - 1].Srapm)})` : ""}. ${jsT.filter((j) => j.SL != null && j.SL > 0).length} de sus ${jsT.length} jugadores con ${c.minMin ? `${c.minMin} minutos o más` : "minutos"} tienen nivel por encima del jugador medio de su liga.` : `Plantilla de ${E(nomE)} con su nivel frente a los jugadores de su liga.`; })();
    const comp = composicion(c), nCards = comp ? 9 : 12;
    const imp = jsT.filter((j) => j.Srapm != null && (j.min || 0) >= 150).sort((a, b) => b.Srapm - a.Srapm);
    const rhJ = comp ? 16 : 19, nJ = comp ? 9 : 12;
    const impSVG = imp.length >= 3 ? divergentes(imp.slice(0, nJ).map((j) => ({ nom: j.corto || j.ape, v: j.Srapm, txt: ESC.txt(j.Srapm), sub: ok(j.mpg) ? `${N(j.mpg, 0)}'` : "" })), { max: 100, lw: 120, w: 330, rh: rhJ, aria: "Impacto en pista" }) : "";
    const nivSVG = jsT.filter((j) => j.SL != null).length >= 3 ? divergentes(jsT.filter((j) => j.SL != null).sort((a, b) => b.SL - a.SL).slice(0, nJ).map((j) => ({ nom: j.corto || j.ape, v: j.SL, txt: ESC.txt(j.SL) })), { max: 100, lw: 120, w: 330, rh: rhJ, aria: "Nivel de cada jugador" }) : "";
    const notaJ = `Medias por partido de ${E(t)} (liga regular). Nivel: valoración global del jugador frente a los jugadores de su liga (escala ±100, 0 = jugador medio de su liga, ponderado por minutos). Impacto: valor v4.0 de cada jugador (RAPM multiliga con prior del perfil: puntos que suma su equipo con él en pista descontando compañeros y rivales), en la misma escala${comp && (imp.length > nJ || jsT.length > nJ) ? `; en las barras, los ${nJ} primeros` : ""}. Color junto al nombre: su estilo de juego. Rol del simulador; filete discontinuo, estimado por minutos.${notaMinEq(c)}`;
    const cards = jsT.slice(0, nCards).map((j) => `<div class="ieq-card"><div class="h">${swEst(j.euI)}<b>${E(j.nombre)}</b></div><small>${j.pos ? POSL[j.pos] || j.pos : "–"}${ok(j.edad) ? ` · ${Math.round(j.edad)} años` : ""} · ${j.eu ? E(j.eu) : "estilo s/d"}</small><div class="k"><span>${chipRol(j)}</span><span><em>Min</em>${ok(j.mpg) ? N(j.mpg, 0) : "–"}</span><span><em>Pts</em>${ok(j.pts) ? N(j.pts, 1) : "–"}</span>${j.an && ok(j.an.NC) ? `<span><em class="v40">Nivel Kerno</em><b>${Math.round(j.an.NC)}</b></span><span><em class="v40">Impacto</em><b>${ok(j.an.IM) ? Math.round(j.an.IM) : "–"}</b></span>` : `<span><em>Nivel</em><b class="${ESC.cls(j.SL)}">${j.SL != null ? ESC.txt(j.SL) : "–"}</b></span><span><em>Impacto</em><b class="${ESC.cls(j.Srapm)}">${j.Srapm != null ? ESC.txt(j.Srapm) : "–"}</b></span>`}</div></div>`).join("");
    const conAn = jsT.filter((j) => j.an && ok(j.an.NC));
    const ncSVG = conAn.length >= 3 ? puntosRango(conAn.slice().sort((a, b) => b.an.NC - a.an.NC).slice(0, nJ).map((j) => ({ nom: j.corto || j.ape, v: j.an.NC, lo: j.an.NC_lo80, hi: j.an.NC_hi80, sub: ok(j.an.minutos) ? `${N(j.an.minutos, 0)}'` : "" })), { ref: 50, lw: 120, w: 330, rh: rhJ, aria: "Nivel Kerno de cada jugador" }) : "";
    const imSVG = conAn.filter((j) => ok(j.an.IM)).length >= 3 ? puntosRango(conAn.filter((j) => ok(j.an.IM)).sort((a, b) => b.an.IM - a.an.IM).slice(0, nJ).map((j) => ({ nom: j.corto || j.ape, v: j.an.IM, lo: j.an.IM_lo80, hi: j.an.IM_hi80, sub: ok(j.an.delta_net) ? SG0(j.an.delta_net, 1) : "" })), { ref: 50, lw: 120, w: 330, rh: rhJ, aria: "Impacto de cada jugador" }) : "";
    pags.push({ sec: S2, html: `${ceja(2, "", "La plantilla, jugador a jugador", lead9)}
      <div class="ieq-cards">${cards}</div>
      ${jsT.length > nCards ? `<p class="r3n">Los ${nCards} jugadores con más minutos de ${jsT.length}.</p>` : ""}
      <div class="r3cols c2">${ncSVG ? `<div class="r3blk"><h3>Nivel Kerno de cada jugador</h3>${ncSVG}</div>` : nivSVG ? `<div class="r3blk"><h3>Nivel de cada jugador</h3>${nivSVG}</div>` : "<div></div>"}${imSVG ? `<div class="r3blk"><h3>Impacto de cada jugador</h3>${imSVG}</div>` : impSVG ? `<div class="r3blk"><h3>Impacto en pista</h3>${impSVG}</div>` : "<div></div>"}</div>
      <p class="r3n">${ncSVG || imSVG ? `Nivel Kerno: percentil esperado de su producción (minutos proyectados × puntos por 100 posesiones) entre los de su puesto en ${E(c.ligaNom)}; junto al nombre, sus minutos proyectados. Impacto: percentil de lo que pierde el equipo sin él (50 = nada; junto al nombre, el Net que cambia por 100 posesiones). Punto y rango del 80 %; minutos del motor del Atlas. ` : ""}${notaJ}</p>
      ${comp}` });

    // 03 · veredicto, rendimiento y riesgos
    const S3 = "Veredicto, rendimiento y riesgos";
    const dRk = c.rkPl && c.rkW ? c.rkPl - c.rkW : null;
    const headline = dRk == null ? `${nomE}: ${c.pN != null ? (c.pN >= 65 ? "rendimiento en la franja alta de su liga" : c.pN <= 35 ? "rendimiento en la franja baja de su liga" : "rendimiento en la zona media de su liga") : "estado del equipo"}` : Math.abs(dRk) <= 2 ? `${nomE} rinde lo que corresponde a su plantilla` : dRk > 0 ? `${nomE} rinde por encima de su plantilla` : `${nomE} rinde por debajo de su plantilla`;
    const suerte = T && T.row && ok(T.row.net_rtg) && ok(T.row.net_rtg_suerte) ? T.row.net_rtg - T.row.net_rtg_suerte : null;
    const lectura = [
      c.rkPl && c.rkW ? `Por nivel de jugadores es el ${ord(c.rkPl)} de ${c.nPl} y por balance, el ${ord(c.rkW)} de ${c.nW}${Math.abs(dRk) <= 2 ? ": el colectivo da lo que prometen las piezas." : dRk > 0 ? `: el colectivo suma ${dRk} puestos más de lo que prometen las piezas.` : `: el colectivo queda ${-dRk} puestos por detrás de lo que prometen las piezas.`}` : "",
      ok(r.net) ? `Su diferencia es de <b>${SG(r.net, 1)} puntos por 100 posesiones</b> (${ord(c.rkN)} de ${c.n}), con ${N(r.ortg, 1)} anotados y ${N(r.drtg, 1)} encajados.` : "",
      suerte != null && Math.abs(suerte) >= 1.5 ? `${suerte < 0 ? "Ha tenido el acierto rival en contra" : "Le ha favorecido el fallo rival"}: si los rivales hubieran tirado triples y libres al promedio de la liga, su diferencia sería ${SG(T.row.net_rtg_suerte, 1)}.` : "",
      c.dPy != null && Math.abs(c.dPy) >= 1.5 ? `Ha ganado ${N(Math.abs(c.dPy), 1)} partidos ${c.dPy > 0 ? "más" : "menos"} de los que sugieren sus puntos a favor y en contra: ${c.dPy > 0 ? "ha cerrado bien los partidos igualados" : "se le han escapado partidos igualados"}.` : ""].filter(Boolean).join(" ");
    const notaHtml = c.nota ? c.nota.split(/\n{2,}|\r?\n/).filter((x) => x.trim()).map((x) => `<p>${E(x.trim())}</p>`).join("") : "";
    const cambiar = [];
    if (c.prov) cambiar.push(`La temporada está en curso (${N(r.gp, 0)} partidos): las cifras pueden moverse.`);
    if (c.ent.length > 1) cambiar.push(`Hubo ${c.ent.length} entrenadores: la lectura mezcla etapas distintas.`);
    if (suerte != null && Math.abs(suerte) >= 1.5) cambiar.push(`Parte de su diferencia depende del acierto rival en triples y libres (${SG(suerte, 1)}), que la defensa controla poco.`);
    if (T && T.row && ok(T.row.min_pct_top5_quintetos) && rangoL(T.lgEQ, "min_pct_top5_quintetos", T.row.min_pct_top5_quintetos, 1) > (2 * T.lgEQ.length) / 3) cambiar.push("Rotación muy cambiante: los quintetos tienen poca muestra y su lectura es frágil.");
    const dep = c.jug && c.jug.filter((j) => ok(j.onoff) && j.min >= 300).sort((a, b) => b.onoff - a.onoff)[0];
    if (dep && dep.onoff >= 6) cambiar.push(`Dependencia de ${dep.nombre}: con él en pista el equipo es ${SG(dep.onoff, 1)} por 100 posesiones mejor. Una lesión cambiaría la lectura.`);
    if (!cambiar.length) cambiar.push("Un cambio de entrenador o la baja de uno de sus tres jugadores con más minutos.");
    const largoNota = c.nota ? c.nota.length : 0, hMapa = Math.max(125, 205 - (largoNota ? 40 + Math.ceil(largoNota / 110) * 19 : 0)), mapa = largoNota <= 900 ? mapaLiga(c, { w: 690, h: hMapa }) : ""; // con una valoración muy larga, el mapa cede su sitio
    const kpis3 = `<div class="r3kp big${v4 ? " anc6" : ""}">${v4 ? `<div class="idx"><span>Net proyectado · v4.0</span><b class="${v4.net > 0.5 ? "up" : v4.net < -0.5 ? "dn" : ""}">${SG0(v4.net, 1)}</b><small>${ord(v4.puesto)} de ${v4.n} por plantilla · rango 80 %: ${SG0(v4.lo80, 1)} a ${SG0(v4.hi80, 1)}${CONFK("net_equipo")}</small></div>` : ""}<div class="idx"><span>Diferencia de puntos</span><b class="${ESC.cls(Snet)}">${Snet != null ? ESC.txt(Snet) : "–"}</b><small>${ok(r.net) ? `${SG(r.net, 1)} por 100 posesiones · escala de su liga` : ""}</small></div>
        <div><span>Balance</span><b>${balTxt}</b><small>${pctW != null ? `${N(pctW, 0)} % · ${ord(c.rkW)} de ${c.nW}` : ""}</small></div>
        <div><span>Victorias esperadas</span><b>${ok(c.py) ? N(c.py, 1) : "–"}</b><small>${c.dPy != null ? `${SG(c.dPy, 1)} frente a las reales` : "por puntos a favor y en contra"}</small></div>
        <div><span>Sin la suerte rival</span><b>${suerte != null ? SG(T.row.net_rtg_suerte, 1) : "–"}</b><small>${suerte != null ? `${SG(suerte, 1)} de suerte` : "sin jugada a jugada"}</small></div>
        <div><span>En el final igualado</span><b>${T && T.row && ok(T.row.clutch_net_rtg) ? SG(T.row.clutch_net_rtg, 0) : "–"}</b><small>${T && T.row ? `por 100 pos. en ${N(T.row.min_clutch, 0)}'${(T.row.min_clutch || 0) < 30 ? " · muestra corta" : ""}` : ""}</small></div></div>`;
    pags.push({ sec: S3, html: `${ceja(3, "", S3, "")}
      <div class="r3theread"><span class="r3lab">The Read${v4 ? " · entre corchetes, rango del 80 %" : ""}</span><p>${E(headline)}.${v4 ? ` Net proyectado de la plantilla ${SG0(v4.net, 1)} [${SG0(v4.lo80, 1)} a ${SG0(v4.hi80, 1)}] por 100 posesiones, ${ord(v4.puesto)} de ${v4.n} en su liga.` : ok(r.net) ? ` Diferencia de ${SG(r.net, 1)} puntos por 100 posesiones, ${ord(c.rkN)} de ${c.n}.` : ""}</p></div>
      ${notaHtml ? `<div class="r3why callout"><span class="r3tag">Valoración Kerno</span>${notaHtml}</div>` : ""}
      <p class="r3p r3lead2">${lectura}</p>
      ${kpis3}
      <div class="r3cols c2"><div class="r3blk"><h3>Lo que prometen las piezas y lo que da el equipo</h3>${puestosSVG(c)}<p class="r3n">Puesto en su liga por nivel de la plantilla (arriba) y por balance (abajo). Si el punto de abajo está a la izquierda del de arriba, el equipo rinde por encima de sus jugadores.</p></div>
        <div class="r3blk"><h3>Facetas frente a su liga</h3>${[...c.fuertes, ...c.debiles.slice().reverse()].map((m) => `<div class="ieq-fac"><span>${E(m.nm)}</span>${barraP(m.p, { w: 120 })}<b class="${tono(m.p, m.dir)}">${Math.round(m.p)}</b></div>`).join("") || `<p class="r3n">Ninguna faceta se separa con claridad de la media.</p>`}<p class="r3n">Percentil en su liga. Arriba, lo que sostiene al equipo; abajo, lo que le cuesta.</p></div></div>
      ${v4 ? ligaV40(c) : ""}
      ${mapa && !v4 ? `<div class="r3blk"><h3>Lo que vale su plantilla y lo que gana</h3>${mapa}<p class="r3n">Cada punto es un equipo de ${E(c.ligaNom)}: a la derecha, plantilla de más nivel frente a las de su liga (escala ±100, 0 = plantilla media); arriba, ${c.mapaY === "wp" ? "más victorias" : "más diferencia de puntos por 100 posesiones (sin balance oficial en esta fase)"}. La línea discontinua es lo esperable por nivel${c.esperado != null && c.mapaY === "wp" && pctW != null ? `: con su plantilla, lo esperable sería un ${N(c.esperado, 0)} % de victorias y lleva un ${N(pctW, 0)} %` : c.esperado != null && c.mapaY === "net" ? `: con su plantilla, lo esperable sería ${SG(c.esperado, 1)} y está en ${SG(r.net, 1)}` : ""}. Por encima de la línea, el equipo rinde más de lo que prometen sus jugadores.</p></div>` : ""}
      <div class="r3cols"><div class="r3wwc"><span class="r3lab">What would change our mind</span><ul class="r3l">${cambiar.slice(0, 4).map((x) => `<li><span>${E(x)}</span></li>`).join("")}</ul></div>
        <div class="r3blk"><h3>Cómo se ha leído</h3><p class="r3n">Cifras de ${E(FNOM[c.s.fase])} frente a los ${c.n} equipos de ${E(c.ligaNom)}: percentil y puesto dentro de su liga. Todas las escalas ±100 tienen 0 = media de su liga: un equipo se lee con la vara de su competición, nunca trasladado a otra.${balNota}</p></div></div>` });

    // 04 · huella del entrenador (estilo, minutos y trayectoria; tiempos muertos en la segunda hoja)
    const S4 = "Huella del entrenador";
    const hEnt = paginaEntrenador(c); if (hEnt) pags.push({ sec: S4, html: hEnt });
    const hTM = paginaTiempos(c); if (hTM) pags.push({ sec: S4, html: hTM });

    // 05 · minutos, roles y estructura de la rotación
    if (T) {
      const S5 = "Minutos, roles y estructura de la rotación";
      const gm = gmin(c.l), js = c.jug.filter((j) => j.mpg >= 0.5).slice(0, 13), row = T.row, nL = T.lgEQ.length;
      const rk = (k, dir = 1) => rangoL(T.lgEQ, k, row[k], dir);
      const rkE = rk("min_pct_top5_quintetos"), est = rkE == null ? "" : rkE <= nL / 3 ? "muy estable, con unidades reconocibles" : rkE > (2 * nL) / 3 ? "muy cambiante: casi ningún quinteto se repite" : "de estabilidad intermedia";
      const lead6 = `Rotación ${est}: sus cinco quintetos más usados juegan el <b>${PC(row.min_pct_top5_quintetos, 0)}</b> de los minutos (${ord(rkE)} más estable de ${nL}). Usa <b>${N(row.jugadores_rotacion, 0)} jugadores de rotación</b> y ${N(row.quintetos_distintos, 0)} quintetos distintos.`;
      const ESTR = [["min_pct_top5_quintetos", "Estabilidad", 1, "cambiante", "estable", "Minutos de sus 5 quintetos más usados."], ["jugadores_rotacion", "Jugadores de rotación", 0, "corta", "larga", "Jugadores con al menos el 25 % de los minutos."], ["hhi_minutos", "Concentración de minutos", 0, "repartidos", "concentrados", "Alto: pocos jugadores acaparan los minutos."], ["min_pct_quinteto_principal", "Peso del quinteto principal", 1, "bajo", "alto", "Minutos del quinteto más usado."], ["hhi_pagerank_asistencias", "Centralización del pase", 0, "coral", "centralizado", "Alto: el juego pasa por pocos jugadores."]];
      const cierra = c.jug.filter((j) => j.cie > 0).sort((a, b) => b.cie - a.cie).slice(0, 5), clutch = c.jug.filter((j) => j.clutch > 0).sort((a, b) => b.clutch - a.clutch).slice(0, 5);
      const roles = (() => { const o = {}; js.forEach((j) => { if (j.rol) o[j.rol] = (o[j.rol] || 0) + 1; }); return ["GO_TO_GUY", "TITULAR", "ROTACION", "PROFUNDIDAD", "RESIDUAL"].filter((k) => o[k]).map((k) => `${o[k]} ${ROLN[k].toLowerCase()}`).join(" · "); })();
      const heat = `<table class="r3t ieq-q cmp"><thead><tr><th>Jugador</th><th>Rol</th><th class="num">Min/p</th><th class="num">1.º C</th><th class="num">2.º C</th><th class="num">3.º C</th><th class="num">4.º C</th><th class="num">Titular</th><th class="num">Cierra</th></tr></thead><tbody>${js.map((j) => `<tr><td><b>${E(j.corto)}</b></td><td>${chipRol(j)}</td><td class="num"><b>${N(j.mpg, 1)}</b></td>${j.q.map((v) => `<td class="num hc" style="${celda(v, gm / 4)}">${N(v, 1)}</td>`).join("")}<td class="num">${N(j.tit, 0)}</td><td class="num">${N(j.cie, 0)}</td></tr>`).join("")}</tbody></table>`;
      pags.push({ sec: S5, html: `${ceja(5, "", S5, lead6)}
        <div class="r3cols mn"><div class="r3blk"><h3>Minutos por partido, cuarto a cuarto</h3>${minutosSVG(js, gm, { cuartos: true, w: 380, rh: 15 })}<p class="r3n">Cada barra son los minutos por partido de un jugador, partidos por cuartos. ${roles ? `Roles: ${roles}.` : ""}${notaMinEq(c)}</p></div>
          <div class="r3blk"><h3>Quién cierra los partidos</h3><ul class="r3rank">${cierra.map((j, i) => `<li><span>${i + 1}</span><span>${E(j.nombre)}</span><b>${N(j.cie, 0)} de ${N(j.gp, 0)}</b></li>`).join("")}</ul><p class="r3n">Partidos que terminó en pista.</p>
            <h3 style="margin-top:12px!important">Quién juega el final igualado</h3><ul class="r3rank">${clutch.map((j, i) => `<li><span>${i + 1}</span><span>${E(j.nombre)}</span><b>${N(j.clutch, 0)}'</b></li>`).join("")}</ul><p class="r3n">Minutos en los últimos 5 minutos con el marcador a 5 puntos o menos.</p></div></div>
        <div class="r3blk"><h3>Cómo se reparte el juego frente a su liga</h3>${ESTR.map(([k, n, d, a, b, q]) => `<div class="ieq-tr"><div><b>${n}</b><small>${q}</small></div>${tira(T.lgEQ.map((x) => [x[k], x === row]).filter((x) => ok(x[0])), { neu: true, w: 300, h: 26, izq: a, der: b, aria: n })}<div class="ieq-trv"><b class="neu">${N(row[k], d)}${/pct/.test(k) ? " %" : ""}</b><small>media ${N(media(T.lgEQ, k), d)}</small></div></div>`).join("")}</div>
        <div class="r3blk"><h3>Quién juega y cuándo</h3>${heat}<p class="r3n">Minutos por partido de cada jugador en cada cuarto (de ${gm / 4}); más oscuro, más minutos. «Titular» y «Cierra»: partidos que empezó y que terminó en pista. Rol del simulador${js.some((j) => j.rolEst) ? "; filete discontinuo, estimado por minutos" : ""}.</p></div>`, cls: "cmp" });
    }

    // 06 · evaluación ofensiva y creación
    const S6 = "Evaluación ofensiva y creación";
    const tiraM = (k, izq, der, h) => { const m = c.met[k]; return `<div class="ieq-tr"><div><b>${E(m.nm)}</b><small>${E(m.q)}</small></div>${tira(m.vals, { dir: m.dir === -1 ? -1 : 1, p: m.p, neu: m.dir === 0, w: 300, h, izq, der, aria: m.nm })}<div class="ieq-trv"><b class="${tono(m.p, m.dir)}">${N(m.v, m.d)}</b><small>${m.dir === 0 ? `media ${N(m.m, m.d)}` : `${ord(m.rk)} de ${c.n}`}</small></div></div>`; };
    const mO = c.met, ataqueLead = `Anota <b>${N(mO.ortg.v, 1)} puntos por 100 posesiones</b> (${ord(mO.ortg.rk)} de ${c.n}, media ${N(mO.ortg.m, 1)}). ${lecturaAtaque(c)}`;
    const reparto = c.jug && c.jug.some((j) => ok(j.pts)) ? (() => { const js = c.jug.filter((j) => ok(j.pts) && j.gp > 0).map((j) => ({ ...j, ptsT: j.pts * j.gp })).sort((a, b) => b.ptsT - a.ptsT), tot = (c.jugTodos || c.jug).filter((j) => ok(j.pts) && j.gp > 0).reduce((a, j) => a + j.pts * j.gp, 0); if (!tot) return ""; const top = js.slice(0, 6);
      return `<div class="r3blk"><h3>Quién pone los puntos</h3>${barras(top.map((j) => ({ nom: j.corto, v: 100 * j.ptsT / tot, txt: `${N(100 * j.ptsT / tot, 0)} %`, sub: `${N(j.pts, 1)} pts/p` })), { max: Math.max(25, ...top.map((j) => 100 * j.ptsT / tot)), lw: 130, w: 330, rh: 21, aria: "Reparto de los puntos" })}<p class="r3n">Parte de los puntos del equipo que anota cada jugador (los seis con más) y su media por partido. ${(() => { const p3 = 100 * top.slice(0, 3).reduce((a, j) => a + j.ptsT, 0) / tot; return `Los tres primeros suman el ${N(p3, 0)} %: ataque ${p3 >= 50 ? "concentrado en pocas manos" : p3 >= 40 ? "con un reparto intermedio" : "repartido"}.`; })()}</p></div>`; })() : "";
    const zonas = T ? zonasSVG(T, { w: 330 }) : "";
    const atacantes = c.jug && c.jug.some((j) => j.Sorapm != null) ? (() => { const js = c.jug.filter((j) => j.Sorapm != null && j.min >= 150).sort((a, b) => b.Sorapm - a.Sorapm); if (js.length < 3) return ""; const sel = js.slice(0, 4).concat(js.length > 6 ? js.slice(-2) : js.slice(4));
      return `<div class="r3blk"><h3>Quién sostiene el ataque</h3>${divergentes(sel.map((j) => ({ nom: j.corto, v: j.Sorapm, txt: ESC.txt(j.Sorapm), sub: `${N(j.mpg, 0)}'` })), { max: 100, lw: 150, w: 690, rh: 16, aria: "Impacto ofensivo" })}<p class="r3n">Impacto ofensivo de cada jugador (puntos que anota de más su equipo con él en pista, descontando compañeros y rivales), escala ±100 con 0 = jugador medio de su liga. Arriba, los cuatro que más aportan; abajo, ${js.length > 6 ? "los dos que menos" : "el resto"}. Jugadores con ${Math.max(150, c.minMin || 0)} minutos o más; junto al nombre, minutos por partido.</p></div>`; })() : "";
    pags.push({ sec: S6, html: `${ceja(6, "", S6, ataqueLead)}
      <div class="r3blk"><h3>Dónde está su ataque dentro de su liga</h3><p class="r3n" style="margin:0 0 6px!important">Cada punto gris es un equipo de ${E(c.ligaNom)}; el punto grande, ${E(nomE)}. A la derecha, mejor. La raya vertical es la mediana.</p>
        ${[["ortg", "menos", "más"], ["efg", "peor", "mejor"], ["tov", "más pérdidas", "menos pérdidas"], ["orb", "menos", "más"], ["ftr", "menos", "más"], ["t3r", "menos triples", "más triples"]].map(([k, a, b]) => tiraM(k, a, b)).join("")}</div>
      <div class="r3cols c2">${zonas ? `<div class="r3blk"><h3>De dónde tira</h3>${zonas}<p class="r3n">Negro: sus tiros por zona; gris: la liga. Derecha: su acierto frente al de la liga.</p></div>` : "<div></div>"}${reparto || "<div></div>"}</div>
      ${atacantes}` });

    // 07 · defensa y control del rival
    const S7 = "Defensa y control del rival";
    const mD = c.met, defLead = `Encaja <b>${N(mD.drtg.v, 1)} puntos por 100 posesiones</b> (${ord(mD.drtg.rk)} de ${c.n}, media ${N(mD.drtg.m, 1)}). ${lecturaDefensa(c)}`;
    const defensores = c.jug && c.jug.some((j) => j.Sdrapm != null) ? (() => { const js = c.jug.filter((j) => j.Sdrapm != null && j.min >= 150).sort((a, b) => b.Sdrapm - a.Sdrapm); if (js.length < 3) return ""; const sel = js.slice(0, 4).concat(js.length > 6 ? js.slice(-2) : []);
      return `<div class="r3blk"><h3>Quién sostiene la defensa</h3>${divergentes(sel.map((j) => ({ nom: j.corto, v: j.Sdrapm, txt: ESC.txt(j.Sdrapm) })), { max: 100, lw: 110, aria: "Impacto defensivo" })}<p class="r3n">Impacto defensivo de cada jugador (puntos que evita su equipo con él en pista, descontando compañeros y rivales), escala ±100 con 0 = jugador medio de su liga. Arriba, los cuatro que más aportan; abajo, ${js.length > 6 ? "los dos que menos" : "el resto"}. Jugadores con ${Math.max(150, c.minMin || 0)} minutos o más.</p></div>`; })() : "";
    const rebote = `<div class="r3blk"><h3>El rebote, en las dos canastas</h3><div class="r3mini ieq-reb"><div><span>Rebote ofensivo</span><b class="${tono(c.met.orb.p, 1)}">${PC(c.met.orb.v, 1)}</b><small>${pTxt(c.met.orb.p)}</small></div><div><span>Rebote defensivo</span><b class="${tono(c.met.drb.p, 1)}">${PC(c.met.drb.v, 1)}</b><small>${pTxt(c.met.drb.p)}</small></div><div><span>Robos</span><b class="${tono(c.met.stl.p, 1)}">${N(c.met.stl.v, 1)}</b><small>${pTxt(c.met.stl.p)}</small></div><div><span>Tapones</span><b class="${tono(c.met.blk.p, 1)}">${N(c.met.blk.v, 1)}</b><small>${pTxt(c.met.blk.p)}</small></div></div><p class="r3n">Rebote: parte de los rebotes disponibles que captura. Robos: por 100 posesiones rivales. Tapones: parte de los tiros de 2 rivales que tapona.</p></div>`;
    const stops = bloqueStops(c);
    pags.push({ sec: S7, html: `${ceja(7, "", S7, defLead)}
      <div class="r3blk"><h3>Dónde está su defensa dentro de su liga</h3><p class="r3n" style="margin:0 0 6px!important">Cada punto gris es un equipo de ${E(c.ligaNom)}; el grande, ${E(nomE)}. A la derecha, mejor defensa.</p>
        ${[["drtg", "encaja más", "encaja menos"], ["oefg", "concede más acierto", "concede menos"], ["otov", "fuerza menos", "fuerza más"], ["drb", "menos", "más"], ["oftr", "concede más", "concede menos"], ["ot3", "más acierto rival", "menos"], ["stl", "menos", "más"], ["blk", "menos", "más"]].map(([k, a, b]) => tiraM(k, a, b, stops ? 28 : 34)).join("")}</div>
      <div class="r3cols c2">${defensores || "<div></div>"}<div>${rebote}</div></div>
      ${stops}`, cls: stops ? "cmp" : "" });

    if (T) {
      // 08 · quintetos de referencia
      const S8 = "Quintetos de referencia", row = T.row;
      const thrQ = umbral(T.Q.map((q) => q.poss), 8, 120, 5, 15), qf = T.Q.filter((q) => q.poss >= thrQ && q.u.every(okI)).sort((a, b) => b.net_rtg_aj - a.net_rtg_aj);
      const top = qf.slice(0, 5), bot = qf.length > 5 ? qf.slice(-Math.min(3, qf.length - 5)).reverse() : [];
      const jDe = (i) => (c.jugTodos || c.jug).find((j) => j.j === i) || { j: i, corto: snJ(c, i), pos: (c.D.J[i] || {}).pos3, euC: null, euI: null };
      const nomQ = (q) => q.u.map(jDe).sort((a, b) => ({ E: 0, A: 1, I: 2 }[a.pos] ?? 1) - ({ E: 0, A: 1, I: 2 }[b.pos] ?? 1)).map((j) => j.corto).join(" · ");
      const qTit = qDeNombres(c, row.quinteto_titular_habitual), qPri = qDeNombres(c, row.quinteto_principal);
      // quinteto titular de mayor impacto: entre los cincos que empezaron 2 partidos o más, el de más diferencia ajustada en sus minutos juntos
      const qIni = ((c.XE && c.XE.quintetos_iniciales) || []).map((x) => { const u = x.unidad.split("|").map((p) => c.pix.get(p)); if (u.some((i) => i == null)) return null; const k = u.slice().sort((a, b) => a - b).join("-"); return { ...x, u, q: T.Q.find((q) => q.u.join("-") === k) || null }; }).filter(Boolean);
      const candI = qIni.filter((x) => x.partidos >= 2 && x.q && ok(x.q.net_rtg_aj) && (x.q.poss || 0) >= thrQ).sort((a, b) => b.q.net_rtg_aj - a.q.net_rtg_aj), qImp = candI[0] || null;
      const esHab = qImp && qTit && qTit.q && qImp.q === qTit.q;
      const SQ = (v) => SV(v, T.vQ);
      const tarj = (tit, m, kv, nota) => !m ? `<div class="r3blk"><h3>${tit}</h3><p class="r3n">No se pudo identificar el quinteto.</p></div>` : `<div class="r3blk"><h3>${tit}</h3>${pista(m.u.map((i) => { const j = jDe(i); return { ...j, sub: j.mpg ? `${N(j.mpg, 0)}'` : "" }; }))}<div class="r3yo ieq-kv" style="grid-template-columns:repeat(${Math.max(4, kv.length)},1fr)">${kv.map(([a, b]) => `<div><span>${a}</span><b>${b}</b></div>`).join("")}</div><p class="r3n">${nota}</p></div>`;
      const kvQ = (m, extra) => [...extra, ["Minutos", m && m.q ? `${N(m.q.min, 0)}'` : "–"], ["Diferencia ajustada", m && m.q ? `${SG(m.q.net_rtg_aj, 1)}` : "–"], ["Anota / encaja", m && m.q ? `${N(m.q.ortg, 0)} / ${N(m.q.drtg, 0)}` : "–"]];
      const nIni = qIni.length, nIni2 = qIni.filter((x) => x.partidos >= 2).length;
      const tit = qImp ? tarj("Quinteto titular de mayor impacto", qImp, kvQ(qImp, [["Partidos de inicio", `${N(qImp.partidos, 0)} de ${N(row.gp, 0)}`], ["Balance al empezar", `${N(qImp.victorias, 0)}-${N(qImp.partidos - qImp.victorias, 0)}`]]),
          `De los ${N(nIni, 0)} cincos iniciales que usó, ${N(nIni2, 0)} empezaron dos partidos o más: entre ellos, con ${N(thrQ, 0)} posesiones juntos o más, este es el que más rinde (diferencia ajustada por muestra).${esHab ? " Coincide con su quinteto titular habitual." : qTit && qTit.q ? ` El titular habitual (${N(row.partidos_quinteto_titular, 0)} partidos de inicio) está en ${SG(qTit.q.net_rtg_aj, 1)}.` : ""}`)
        : tarj("Quinteto titular habitual", qTit, kvQ(qTit, [["Partidos de inicio", `${N(row.partidos_quinteto_titular, 0)} de ${N(row.gp, 0)}`]]), `El cinco que más veces empieza. Usó ${N(row.quintetos_titulares_distintos, 0)} quintetos iniciales distintos; sin el detalle de cada inicio no se puede elegir el de mayor impacto.`);
      const pri = tarj("Quinteto principal", qPri, kvQ(qPri, [["% de minutos", PC(row.min_pct_quinteto_principal, 1)]]), "El cinco que más minutos juega junto, empiece o no.");
      const filasQ = (arr) => arr.map((q) => ({ nom: corta(nomQ(q), 58), v: SQ(q.net_rtg_aj), txt: SG(q.net_rtg_aj, 1), sub: `${N(q.min, 0)}'` }));
      const trios = T.T3.filter((q) => q.poss >= umbral(T.T3.map((x) => x.poss), 10, 300, 10, 40) && q.u.every(okI)).sort((a, b) => b.net_rtg_aj - a.net_rtg_aj).slice(0, 4);
      const lead7 = qf.length ? `El quinteto que más rinde con ${N(thrQ, 0)} posesiones o más es <b>${E(nomQ(qf[0]))}</b>: ${SG(qf[0].net_rtg_aj, 1)} por 100 posesiones en ${N(qf[0].min, 0)} minutos.${qImp ? ` Entre los que salen de inicio, el de más impacto está en ${SG(qImp.q.net_rtg_aj, 1)}.` : qTit && qTit.q ? ` El titular habitual está en ${SG(qTit.q.net_rtg_aj, 1)}.` : ""}` : "Ningún quinteto llega a la muestra mínima para leerlo con garantías.";
      pags.push({ sec: S8, html: `${ceja(8, "", S8, lead7)}
        <div class="r3cols c2">${tit}${pri}</div>
        <div class="r3blk"><h3>Los quintetos que más suman y los que menos</h3>${top.length ? divergentes(filasQ(top).concat(bot.length ? [{ nom: "", v: 0, txt: "" }] : [], filasQ(bot)).filter((x) => x.nom || x.txt === ""), { max: 100, lw: 330, w: 690, rh: 22, aria: "Diferencia ajustada de los quintetos" }) : `<p class="r3n">Ningún quinteto llega al mínimo de posesiones.</p>`}<p class="r3n">Diferencia de puntos por 100 posesiones de cada quinteto, ajustada por muestra (un quinteto con pocas posesiones se acerca a la media), con ${N(thrQ, 0)} posesiones o más. Barras en escala ±100 frente a los quintetos de su liga; a la derecha, la cifra por 100 posesiones; junto al nombre, los minutos juntos.${bot.length ? " Arriba, los cinco que más suman; tras el hueco, los que menos." : ""}${notaMinEq(c)}</p></div>
        ${trios.length ? `<div class="r3blk"><h3>${trios[0].net_rtg_aj > 0 ? "Tríos que sostienen al equipo" : "Los tríos que más rinden"}</h3>${divergentes(trios.map((q) => ({ nom: corta(q.u.map((i) => snJ(c, i)).join(" · "), 58), v: SV(q.net_rtg_aj, T.vT3), txt: SG(q.net_rtg_aj, 1), sub: `${N(q.min, 0)}'` })), { max: 100, lw: 330, w: 690, aria: "Tríos" })}<p class="r3n">Los tríos con más diferencia ajustada entre los que más juegan juntos. Un trío fuerte es una base para construir quintetos.</p></div>` : ""}
        ${leyendaEst(null, "Color de cada jugador en la pista, su estilo:")}` });

      // 09 · relaciones y red de pases
      const S9 = "Relaciones y red de pases";
      const thrP = umbral(T.P.map((p) => p.min), 12, 250, 10, 60), ps = T.P.filter((p) => p.min >= thrP && ok(p.sinergia) && okI(p.a) && okI(p.b)).sort((a, b) => b.sinergia - a.sinergia);
      const pTop = ps.slice(0, 5), pBot = ps.length > 5 ? ps.slice(-3).reverse() : [];
      const filaPj = (p) => ({ nom: corta(`${snJ(c, p.a)} + ${snJ(c, p.b)}`, 30), v: SV(p.sinergia, T.vP), txt: SG(p.sinergia, 1), sub: `${N(p.min, 0)}'` });
      const dist = c.jug.filter((j) => j.astD > 0).sort((a, b) => b.astD - a.astD).slice(0, 4), dest = c.jug.filter((j) => ok(j.pr)).sort((a, b) => b.pr - a.pr).slice(0, 4), lk = T.A.filter((a) => okI(a.p) && okI(a.r)).sort((a, b) => b.ast - a.ast).slice(0, 5);
      const lead8 = `${ps.length ? `La pareja que más se potencia es <b>${E(snJ(c, ps[0].a))} y ${E(snJ(c, ps[0].b))}</b>: juntos rinden ${SG(ps[0].sinergia, 1)} por 100 posesiones por encima de lo que suman por separado.` : ""}${dist.length && dest.length ? ` ${E(dist[0].nombre)} es quien más asiste y ${E(dest[0].nombre)}, el destino principal del juego.` : ""}`;
      const minEf = T.E.filter((e) => (e.fga_con || 0) >= 80 && ok(e.d_pts100)).length >= 4 ? 80 : 40, efectos = T.E.filter((e) => (e.fga_con || 0) >= minEf && ok(e.d_pts100) && okI(e.xi) && okI(e.yi)).sort((a, b) => b.d_pts100 - a.d_pts100).slice(0, 4);
      const parT = `<div class="r3blk"><h3>Parejas que más suman y las que menos</h3>${pTop.length ? divergentes(pTop.map(filaPj).concat(pBot.length ? [{ nom: "", v: 0, txt: "" }] : [], pBot.map(filaPj)), { max: 100, lw: 170, w: 330, aria: "Sinergia de parejas" }) : `<p class="r3n">Sin parejas con minutos suficientes.</p>`}<p class="r3n">Sinergia: cuánto rinde la pareja junta por encima de lo que aporta cada uno por separado, por 100 posesiones (barras en escala ±100 frente a las parejas de su liga), con ${N(thrP, 0)} minutos juntos o más${T.pf !== c.s.fase ? " (toda la temporada: en playoffs no se calculan parejas)" : ""}.${notaMinEq(c)}</p></div>`;
      const listaRed = `<div class="ieq-red3"><div><span class="r3lab">Quién reparte</span><ul class="r3rank">${dist.map((j, i) => `<li><span>${i + 1}</span><span>${E(j.corto)}</span><b>${N(j.astD, 0)}</b></li>`).join("")}</ul></div><div><span class="r3lab">A quién llega el juego</span><ul class="r3rank">${dest.map((j, i) => `<li><span>${i + 1}</span><span>${E(j.corto)}</span><b>${N(100 * j.pr, 0)} %</b></li>`).join("")}</ul></div><div><span class="r3lab">Conexiones más repetidas</span><ul class="r3rank">${lk.map((a, i) => `<li><span>${i + 1}</span><span>${E(snJ(c, a.p))} <i class="k-ar" aria-hidden="true"></i> ${E(snJ(c, a.r))}</span><b>${N(a.ast, 0)}</b></li>`).join("")}</ul></div></div>`;
      const efT = efectos.length ? `<div class="r3blk"><h3>Quién mejora a quién</h3><ul class="r3l up">${efectos.map((e) => `<li><b>${E(snJ(c, e.xi))} <i class="k-ar" aria-hidden="true"></i> ${E(snJ(c, e.yi))}</b><span>con ${E(snJ(c, e.xi))} en pista, ${E(snJ(c, e.yi))} produce ${SG(e.d_pts100, 1)} puntos más por 100 posesiones${ok(e.d_efg) ? ` y su acierto cambia ${SG(e.d_efg, 1)} pp` : ""}</span></li>`).join("")}</ul><p class="r3n">Cambio en el compañero cuando comparten pista frente a cuando no, con ${minEf} tiros o más juntos. Son efectos con mucho ruido: una pista para el vídeo, no una conclusión.</p></div>` : "";
      const enRed = [...new Set(c.jug.filter((j) => j.astD + j.astR > 0).slice(0, 10).map((j) => j.euI).filter(ok))].sort((a, b) => a - b);
      pags.push({ sec: S9, html: `${ceja(9, "", S9, lead8)}
        <div class="r3cols c2"><div class="r3blk"><h3>La red de pases</h3>${T.A.length ? redSVG(c, { w: 330, h: 300 }) : `<p class="r3n">Sin asistencias registradas.</p>`}${T.A.length ? leyendaEst(enRed) : ""}<p class="r3n">Cada círculo es un jugador (tamaño: asistencias dadas y recibidas; color: su estilo de juego). Las líneas unen a quien asiste con quien anota; en negro, las tres conexiones más repetidas.${notaMinEq(c)}</p></div>
          ${parT}</div>
        <div class="r3blk"><h3>Centro de la red</h3>${listaRed}</div>
        ${efT}` });
    }

    // anexo · glosario
    const G = [["Net proyectado · Nivel Kerno · Impacto", "v4.0: puntos por 100 posesiones que proyecta la plantilla frente a su liga (rango del 80 %); y por jugador, de 0 a 100, su producción esperada entre los de su puesto y lo que pierde el equipo sin él (50 = nada)."],
      ["Percentil", "De 0 a 100 frente a los equipos de su liga: 80 = supera al 80 % de ellos; 50 = el mediano. Si menos es mejor, ya está invertido."], ["Escala ±100", "Nivel, impacto, diferencia y sinergias se expresan de −100 a +100; 0 es la media de su liga y ±46, una desviación típica de su liga."], ["Nivel de la plantilla", "Media del nivel de sus jugadores ponderada por minutos, frente a las plantillas de su liga."], ["Diferencia de puntos", "Puntos anotados menos encajados por cada 100 posesiones (Net). Por 100 posesiones para comparar equipos rápidos y lentos."],
      ["Sin la suerte rival", "La misma diferencia si los rivales hubieran tirado triples y libres al promedio de la liga, lo que menos controla la defensa."], ["Victorias esperadas", "Las que corresponden a sus puntos a favor y en contra (fórmula pitagórica, exponente 14)."], ["Final igualado", "Últimos 5 minutos con el marcador a 5 puntos o menos (clutch)."],
      ["Acierto efectivo (eFG%)", "Acierto de campo con el triple valiendo uno y medio."], ["Rebote ofensivo / defensivo", "Parte de los rebotes disponibles que captura en cada canasta."], ["Tiros libres provocados", "Tiros libres por cada 100 tiros de campo (FTr)."],
      ["Stop", "Posesión del rival que acaba sin puntos, contada en el jugada a jugada. % de stops: stops entre posesiones del rival."], ["Tiempo muerto: parcial", "Puntos propios menos los del rival en los 2 minutos anteriores o siguientes a un tiempo muerto pedido por el equipo."], ["Primera posesión tras tiempo muerto", "Puntos de la primera posesión propia que empieza en los 30 segundos siguientes (jugada de pizarra, ATO)."],
      ["Estabilidad", "Minutos que juegan sus cinco quintetos más usados. Alta: unidades fijas; baja: muchas combinaciones."], ["Jugadores de rotación", "Los que están en pista al menos en el 25 % de los minutos del equipo."], ["Quinteto titular de mayor impacto / principal", "Entre los cincos que empiezan dos partidos o más, el de más diferencia ajustada / el que más minutos juega junto."],
      ["Diferencia ajustada", "La de un quinteto, trío o pareja corregida por muestra: con pocas posesiones se acerca a la media."], ["Sinergia", "Cuánto rinde una pareja junta por encima de lo que aporta cada uno por separado."], ["Impacto (valor v4.0)", "RAPM multiliga de la v4.0: puntos por 100 posesiones que suma su equipo con él en pista, descontando compañeros y rivales."],
      ["Rol", "Residual (menos de 5'), Profundidad (5–15'), Rotación (15–22'), Titular (más de 22' y de inicio) y Go-to-guy (referencia ofensiva)."], ["Destino del juego", "Peso de un jugador como receptor de la red de asistencias (PageRank): hacia dónde fluye el juego."]];
    const estG = EUS().map((e, k) => `<div><dt>${swEst(k)}${E(e.nombre)}</dt><dd>${E(e.equipo || e.definicion || "")}</dd></div>`).join("");
    const ligasV = `<div class="r3blk"><h3>Un equipo se lee en su liga</h3><p class="r3p">Cada cifra de este informe compara al equipo con los demás equipos de ${E(c.ligaNom)} y a sus jugadores con los jugadores de esa competición. Un equipo no se traslada de golpe a otra liga: su rendimiento depende de los rivales, el calendario, el reglamento y el criterio de registro de su competición. Para valorar a un jugador fuera de su liga está la lectura de fichaje, que traduce sus cifras a la liga de destino.</p></div>`;
    pags.push({ sec: "Glosario", anexo: true, html: `${ceja(0, "", "Glosario: términos, escalas y estilos", "").replace("Sección #N#", "Anexo").replace(/<b class="r3num">#N#<\/b>/, '<b class="r3num">A</b>')}<dl class="r3glos">${G.map(([a, x]) => `<div><dt>${E(a)}</dt><dd>${E(x)}</dd></div>`).join("")}</dl>
      <div class="r3blk"><h3>Estilos de juego</h3><dl class="r3glos est">${estG}</dl><p class="r3n">En este informe, cada estilo tiene su color de marca (verde Racing, salvia, jade, oliva, verde claro y jade claro), distinto del azul y el naranja, que marcan mejor y peor, y del violeta, que marca los rasgos de estilo de las cifras.</p></div>
      ${ligasV}
      <p class="r3n">Fuentes: actas oficiales y jugada a jugada de cada competición, datos públicos a ${E(fecha)}. Modelos de Kerno Analytics. Con menos de 15 partidos o 300 minutos por jugador, las cifras oscilan mucho.</p>` });
    pags.push({ portada: true, back: true, html: `<img src="${INF_LOGO.vn}" alt="KERNO Analytics" class="cvback-logo"><p class="cvclaim">Make the right read.</p><p class="cvfine">Kerno Analytics · Documento confidencial</p>` });

    // números de sección e índice de la portada
    const Nn = pags.length; let num = 0;
    pags.forEach((p) => { if (p.portada) return; if (p.anexo) { p.num = "A"; return; } num = p.sec === (pags[pags.indexOf(p) - 1] || {}).sec ? num : num + 1; p.num = num; p.html = p.html.split("#N#").join(String(num).padStart(2, "0")); });
    const vistos = new Set();
    pags[0].html = pags[0].html.replace("#INDICE#", pags.map((p, i) => { if (p.portada || vistos.has(p.num)) return ""; vistos.add(p.num); return `<li><span>${p.anexo ? "Anexo" : String(p.num).padStart(2, "0")}</span><span>${E(p.sec)}</span><b>${i + 1}</b></li>`; }).join(""));
    return pags.map((p, i) => hoja(p.html, { ...p, cls: `v${V}${p.cls ? " " + p.cls : ""}`, n: i + 1, N: Nn, fecha, extra }));
  }
  // ------------------------------------------------------------------------------------------- 3b. el entrenador
  // Huella del entrenador con lo que sí se mide en actas y jugada a jugada: cómo quiere jugar (ritmo, tiro, pase, rebote,
  // presión, qué concede), cómo reparte los minutos (turnos, banquillo, cierres, jóvenes, tamaño, quintetos iniciales) y su
  // trayectoria en los datos (todas sus etapas, en cada liga con la vara de esa liga). Sistemas y coberturas: requieren vídeo.
  function rasgosRot(D, fase) {
    const by = new Map(); D.on.filter((r) => r.fase === fase && (r.min_on || 0) > 0).forEach((r) => { const a = by.get(r.team_id) || []; a.push(r); by.set(r.team_id, a); });
    const out = [];
    by.forEach((rs, tid) => {
      const M = rs.reduce((a, r) => a + r.min_on, 0); if (!M) return;
      const turnos = rs.reduce((a, r) => a + (r.relevos_por_partido || 0) * (r.gp || 0), 0), tit = rs.filter((r) => (r.titular_partidos || 0) >= 0.5 * (r.gp || 1));
      const qm = (arr, k) => arr.reduce((a, r) => a + r.min_on * (r[k] || 0) / 100, 0), q4 = qm(rs, "pct_min_q4");
      const minDe = (f) => rs.filter((r) => f(D.J[r.j] || {})).reduce((a, r) => a + r.min_on, 0);
      const eq = D.EQ.find((x) => x.team_id === tid && x.fase === fase) || {};
      out.push({ tid, turno: turnos ? M / turnos : null, banq: 100 * (M - tit.reduce((a, r) => a + r.min_on, 0)) / M, cierre: q4 ? 100 * qm(tit, "pct_min_q4") / q4 : null,
        jov: 100 * minDe((p) => ok(p.edad) && p.edad <= 23) / M, inter: 100 * minDe((p) => p.pos3 === "I") / M, qini: ok(eq.quintetos_titulares_distintos) && eq.gp ? eq.quintetos_titulares_distintos : null });
    });
    return out;
  }
  function paginaEntrenador(c) {
    if (!c.ent.length) return "";
    const e0 = c.ent.slice().sort((a, b) => (b.pj || 0) - (a.pj || 0))[0], X = EVX, varios = c.ent.length > 1;
    // trayectoria: todas sus etapas en los datos, cada una leída en su liga
    const etapas = []; Object.entries(X.C).forEach(([k, cl]) => (cl.ent || []).forEach((e) => { if (e.id !== e0.id) return; const row = X.by.get(`${k.split(":").slice(-1)[0]}|regular|${k.split(":")[0]}|${k.split(":").slice(1, -1).join(":")}`) || X.F.find((x) => x.k === k && x.f === "regular") || X.F.find((x) => x.k === k);
      if (!row) return; const lgx = X.F.filter((x) => x.t === row.t && x.f === row.f && x.liga === row.liga), a2 = BY.get(k), ea = a2 && Array.isArray(a2.entrenadores) ? a2.entrenadores.find((x) => x && x.entrenador_id === e.id) : null;
      etapas.push({ k, row, e, varios: (cl.ent || []).length > 1, S: SV(row.L, vara(lgx.filter((x) => ok(x.L)).map((x) => [x.L, 1]))), pR: pctL(lgx, "ritmo", row.ritmo, 1), p3: pctL(lgx, "t3r", row.t3r, 1), pA: pctL(lgx, "astr", row.astr, 1), eu: ea ? ea.eu_etiqueta : null }); }));
    etapas.sort((a, b) => b.row.t.localeCompare(a.row.t) || (b.e.pj || 0) - (a.e.pj || 0));
    const otras = etapas.filter((x) => x.k !== c.r.k);
    const wpj = (f) => { const a = otras.filter((x) => x[f] != null), W = a.reduce((s2, x) => s2 + (x.e.pj || 1), 0); return W ? a.reduce((s2, x) => s2 + x[f] * (x.e.pj || 1), 0) / W : null; };
    const mR = wpj("pR"), m3 = wpj("p3"), mA = wpj("pA");
    const nivelP = (p, lo, mid, hi) => p == null ? "" : p >= 65 ? hi : p <= 35 ? lo : mid;
    // cómo quiere jugar (estilo: ni bueno ni malo)
    const JUEGO = [["ritmo", "Ritmo", "Posesiones por partido.", "lento", "rápido"], ["t3r", "Peso del triple", "Triples por cada 100 tiros.", "ataca dentro", "tira de fuera"], ["astr", "Juego de pase", "Canastas tras asistencia.", "uno contra uno", "pase"],
      ["orb", "Rebote ofensivo", "Va al rebote o protege la transición.", "balance", "rebote"], ["otov", "Presión", "Pérdidas que fuerza al rival.", "espera", "presiona"], ["ot3r", "Qué concede", "Triples que deja intentar al rival.", "niega triples", "niega zona"]];
    const fila = (lab, q, vals, me, iz, de, txt, sub) => `<div class="ieq-rs"><div><b>${E(lab)}</b><small>${E(q)}</small></div>${tira(vals, { neu: true, w: 140, h: 27, izq: iz, der: de, aria: lab })}<div class="ieq-trv"><b class="neu">${txt}</b><small>${E(sub)}</small></div></div>`;
    const juego = JUEGO.map(([k, lab, q, iz, de]) => { const m = c.met[k]; return m && m.v != null ? fila(lab, q, m.vals, true, iz, de, N(m.v, 1), `media ${N(m.m, 1)}`) : ""; }).join("");
    // cómo reparte los minutos
    let reparto = "", rrow = null, RR = [];
    if (c.T) { RR = rasgosRot(c.D, c.s.fase); rrow = RR.find((x) => x.tid === c.s.eq) || null; }
    const MINS = [["turno", "Turnos en pista", "Minutos seguidos antes de sentarse.", "cortos", "largos", 1, "'"], ["banq", "Banquillo", "Minutos de los no titulares.", "pocos", "muchos", 1, " %"],
      ["cierre", "Cierres", "Minutos del 4.º cuarto para titulares.", "suplentes", "titulares", 0, " %"], ["jov", "Jóvenes", "Minutos de jugadores de 23 años o menos.", "pocos", "muchos", 0, " %"],
      ["inter", "Tamaño", "Minutos de interiores.", "bajos", "grandes", 0, " %"], ["qini", "Quinteto inicial", "Cincos iniciales distintos.", "fijo", "cambiante", 0, ""]];
    if (rrow) reparto = MINS.map(([k, lab, q, iz, de, d, u]) => { const vals = RR.filter((x) => ok(x[k])).map((x) => [x[k], x === rrow]); return ok(rrow[k]) && vals.length >= 3 ? fila(lab, q, vals, true, iz, de, N(rrow[k], d) + u, `media ${N(media(RR, k), d)}${u}`) : ""; }).join("");
    const pR = c.met.ritmo.p, p3 = c.met.t3r.p, pA = c.met.astr.p;
    const pT = rrow && ok(rrow.turno) ? pctL(RR, "turno", rrow.turno, 1) : null, pB = rrow && ok(rrow.banq) ? pctL(RR, "banq", rrow.banq, 1) : null, pC = rrow && ok(rrow.cierre) ? pctL(RR, "cierre", rrow.cierre, 1) : null;
    const lead = `${E(e0.n)}${c.ent.length > 1 ? ` (${N(e0.pj, 0)} de los partidos de la temporada)` : ""}: equipo de ritmo ${nivelP(pR, "bajo", "medio", "alto")}, ${nivelP(p3, "que ataca dentro antes que de tres", "con un peso del triple en la media de su liga", "que vive del triple")} y ${nivelP(pA, "con más uno contra uno que pase", "con un juego de pase en la media", "con mucho juego de pase")}.${pT != null ? ` En los minutos, ${nivelP(pT, "da turnos cortos", "da turnos de duración media", "da turnos largos")}${pB != null ? `, ${nivelP(pB, "tira poco del banquillo", "reparte con el banquillo como la media", "tira mucho del banquillo")}` : ""}${pC != null ? ` y ${nivelP(pC, "cierra los partidos con suplentes más que la media", "cierra con titulares como la media", "cierra con sus titulares")}` : ""}.` : ""}`;
    const consist = otras.length >= 1 && mR != null ? `En sus otras ${otras.length} etapas en los datos, sus equipos ${nivelP(mR, "juegan lento", "juegan a un ritmo medio", "juegan rápido")} (percentil medio ${Math.round(mR)}; aquí ${pR != null ? Math.round(pR) : "–"}), ${nivelP(m3, "tiran poco de tres", "tiran de tres como la media", "tiran mucho de tres")} (${m3 != null ? Math.round(m3) : "–"}; aquí ${p3 != null ? Math.round(p3) : "–"}) y ${nivelP(mA, "pasan poco", "pasan como la media", "pasan mucho")} (${mA != null ? Math.round(mA) : "–"}; aquí ${pA != null ? Math.round(pA) : "–"}), siempre frente a su liga de cada año. ${(() => { const d = [[mR, pR], [m3, p3], [mA, pA]].filter(([x, y]) => x != null && y != null).map(([x, y]) => Math.abs(x - y)); return !d.length ? "" : Math.max(...d) <= 25 ? "Este equipo se parece a lo que suele hacer: la huella es suya." : "Este equipo se separa de lo que suele hacer en ritmo, triple o pase: aquí pesa la plantilla, o ha cambiado de idea."; })()}` : "Es su única etapa en los datos (desde 2020-21): no se puede separar su huella de la de esta plantilla.";
    const tray = etapas.length ? `<table class="r3t ieq-tray"><thead><tr><th>Temp.</th><th>Club</th><th>Liga</th><th class="num">PJ</th><th class="num">Balance</th><th class="num">Plantilla</th><th class="num">Ritmo</th><th class="num">Triple</th><th class="num">Pase</th><th>Estilo en su etapa</th></tr></thead><tbody>${etapas.slice(0, 10).map((x) => `<tr class="${x.k === c.r.k ? "yo" : ""}"><td>${E(x.row.t)}</td><td>${E(corta(x.row.eq, 26))}${x.varios ? "*" : ""}</td><td>${E(LC[x.row.liga] || ESC.ligaCorto(x.row.liga))}</td><td class="num">${N(x.e.pj, 0)}</td><td class="num">${ok(x.e.w) ? `${x.e.w}-${x.e.l}` : "–"}</td><td class="num">${x.S != null ? ESC.txt(x.S) : "–"}</td><td class="num">${x.pR != null ? Math.round(x.pR) : "–"}</td><td class="num">${x.p3 != null ? Math.round(x.p3) : "–"}</td><td class="num">${x.pA != null ? Math.round(x.pA) : "–"}</td><td>${E(x.eu || "–")}</td></tr>`).join("")}</tbody></table>
      <p class="r3n">Una fila por club, competición y temporada (las más recientes primero). Plantilla: nivel frente a las de su liga ese año (escala ±100). Ritmo, triple y pase: percentil frente a los equipos de su liga ese año. *Temporada con más de un entrenador: las cifras del equipo mezclan etapas.</p>` : "";
    const nota = `<p class="r3p ieq-lim"><b>Qué no se lee aquí.</b> Esta página sale de actas y jugada a jugada: describe decisiones que se miden. Los sistemas de juego (horns, Spain pick-and-roll, salidas de bloqueo) y las coberturas del bloqueo directo necesitan vídeo; el scouting del cuerpo técnico completa esta lectura.</p>`;
    return `${ceja(0, "", "Huella del entrenador", lead)}
      <dl class="r3id">${[["Entrenador", e0.n + (e0.int ? " (interino)" : "")], ["Etapa", `${fechaC(e0.de)} – ${fechaC(e0.a)}`], ["Partidos", N(e0.pj, 0)], ["Balance", ok(e0.w) ? `${e0.w}-${e0.l}` : "–"], ["Etapas en los datos", N(etapas.length, 0)], ["Clubes", N(new Set(etapas.map((x) => (X.C[x.k] || {}).club)).size, 0)]].map(([a, v]) => `<div><dt>${a}</dt><dd>${E(v)}</dd></div>`).join("")}</dl>
      ${varios ? `<p class="r3n">Temporada con ${c.ent.length} entrenadores: los rasgos del equipo mezclan sus etapas; la trayectoria separa la huella de ${E(e0.n)}.</p>` : ""}
      <div class="r3cols c2 ieq-entc"><div class="r3blk"><h3>Cómo quiere jugar</h3>${juego}</div>${reparto ? `<div class="r3blk"><h3>Cómo reparte los minutos</h3>${reparto}</div>` : ""}</div>
      <p class="r3n">Rasgos de estilo, no de calidad: cada punto gris es un equipo de ${E(c.ligaNom)} y el grande, ${E(c.nombre)}; la raya, la mediana.</p>
      ${etapas.length ? `<div class="r3blk"><h3>Su trayectoria en los datos</h3><p class="r3p" style="margin-bottom:6px!important">${consist}</p>${tray}</div>` : ""}
      ${nota}`;
  }
  const fechaC = (s) => s ? new Date(s + "T12:00:00").toLocaleDateString("es-ES", { day: "numeric", month: "short", year: "2-digit" }) : "–";
  function celda(v, max) { const t = Math.max(0, Math.min(1, (v || 0) / (max || 1))), a = [232, 239, 235], b = [15, 46, 37], m = a.map((x, i) => Math.round(x + (b[i] - x) * t * 0.85)); return `background:rgb(${m.join(",")});color:${t > 0.55 ? "#F3F4F0" : "#0C1210"}`; }
  function pizarraEnt(c) {
    if (!c.ent.length) return `<p class="r3n">Sin datos de entrenador para este equipo y temporada.</p>`;
    const ds = c.ent.map((e) => Date.parse(e.de)).filter(ok), as = c.ent.map((e) => Date.parse(e.a)).filter(ok), t0 = Math.min(...ds), t1 = Math.max(...as), sp = Math.max(1, t1 - t0);
    const line = ds.length && as.length ? `<div class="ieq-tl">${c.ent.map((e, i) => { const a = Date.parse(e.de), b = Date.parse(e.a); if (!ok(a) || !ok(b)) return ""; return `<i style="left:${100 * (a - t0) / sp}%;width:${Math.max(2, 100 * (b - a) / sp)}%;background:${i === c.ent.length - 1 ? C.ink : C.g4}"></i>`; }).join("")}</div><div class="ieq-tlax"><span>${E(fechaC(new Date(t0).toISOString().slice(0, 10)))}</span><span>${E(fechaC(new Date(t1).toISOString().slice(0, 10)))}</span></div>` : "";
    return `${line}<div class="ieq-ents">${c.ent.map((e) => `<div><b>${E(e.n)}</b>${e.int ? "<small>interino</small>" : ""}<span><em>Partidos</em>${N(e.pj, 0)}</span><span><em>Balance</em>${ok(e.w) ? `${e.w}-${e.l}` : "–"}</span><span><em>Nivel plantilla</em>${e.SL != null ? ESC.txt(e.SL) : "–"}</span><span><em>Estilo</em>${E(e.eu || "–")}</span></div>`).join("")}</div>${c.ent.length > 1 ? `<p class="r3n">Cada etapa se mide solo con los partidos que dirigió. Una etapa corta es poco fiable.</p>` : ""}`;
  }
  function lecturaAtaque(c) {
    const m = c.met, out = [];
    if (m.efg.p != null && m.tov.p != null) out.push(m.efg.p >= 65 ? (m.tov.p >= 50 ? "Tira bien y cuida el balón: su ataque se apoya en la calidad de sus tiros." : "Tira bien, pero pierde más balones de lo normal en su liga.") : m.efg.p <= 35 ? (m.orb.p != null && m.orb.p >= 65 ? "Le cuesta meter, y lo compensa con segundas opciones en el rebote ofensivo." : "Le cuesta meter: su acierto está en la parte baja de su liga.") : "Su acierto está en la zona media de su liga.");
    if (m.t3r.p != null) out.push(m.t3r.p >= 70 ? "Es de los equipos que más se apoyan en el triple." : m.t3r.p <= 30 ? "Tira menos triples que la mayoría de su liga: ataca más cerca del aro." : "");
    if (m.ftr.p != null && m.ftr.p >= 70) out.push("Pisa la línea de tiros libres con frecuencia.");
    return out.filter(Boolean).join(" ");
  }
  function lecturaDefensa(c) {
    const m = c.met, out = [];
    if (m.oefg.p != null) out.push(m.oefg.p >= 65 ? "Concede tiros difíciles: el acierto rival está en la parte baja de su liga." : m.oefg.p <= 35 ? "Concede tiros cómodos: el rival acierta más que contra la mayoría." : "El acierto que concede está en la media de su liga.");
    if (m.otov.p != null && m.otov.p >= 70) out.push("Fuerza muchas pérdidas.");
    if (m.drb.p != null) out.push(m.drb.p >= 65 ? "Cierra bien su rebote." : m.drb.p <= 35 ? "Concede segundas opciones en su rebote." : "");
    return out.filter(Boolean).join(" ");
  }

  // ------------------------------------------------------------------------------------------- 4. controles, estado y pintado
  function estado() {
    const s = st.ieq || (st.ieq = {});
    if (!EVX) return { s, temps: [], ligas: [], equipos: [] };
    const temps = [...new Set(EVX.F.map((r) => r.t))].sort().reverse();
    if (!temps.includes(s.temp)) s.temp = temps.includes(ultCompleta()) ? ultCompleta() : temps[0];
    const ligas = ESC.ordenLigas([...new Set(EVX.F.filter((r) => r.t === s.temp).map((r) => r.liga))]);
    if (!ligas.includes(s.liga)) s.liga = ligas.includes("euroleague") ? "euroleague" : ligas[0];
    if (!FASES.some(([f]) => f === s.fase)) s.fase = "regular";
    let equipos = EVX.F.filter((r) => r.t === s.temp && r.liga === s.liga && r.f === s.fase);
    if (!equipos.length && s.fase !== "regular") { s.fase = "regular"; equipos = EVX.F.filter((r) => r.t === s.temp && r.liga === s.liga && r.f === s.fase); }
    equipos = equipos.sort((a, b) => String(a.eq).localeCompare(String(b.eq), "es"));
    if (!equipos.some((r) => r.id === s.eq)) { const al = META.clubes_con_nombre && META.clubes_con_nombre.baskonia, k = al && al.claves.find((x) => x.startsWith(s.liga + ":")), tid = k ? k.split(":")[1] : null; s.eq = equipos.some((r) => r.id === tid) ? tid : (equipos[0] && equipos[0].id); }
    s.ver = "B"; // v1.4: el informe de equipo tiene una sola versión (la antigua «Pizarra»)
    const fases = FASES.filter(([f]) => EVX.by.has(`${s.temp}|${f}|${s.liga}|${s.eq}`));
    return { s, temps, ligas, equipos, fases };
  }
  const opts = (sel, items, val) => { if (!sel) return; sel.innerHTML = items.map(([v, t]) => `<option value="${E(v)}">${E(t)}</option>`).join(""); if (val != null) sel.value = val; };
  function pintarControles() {
    const { s, temps, ligas, equipos, fases } = estado();
    opts($1("#ieqTemp"), temps.map((t) => [t, t + (prov(t) ? " (en curso)" : "")]), s.temp);
    opts($1("#ieqLiga"), ligas.map((l) => [l, LIGAS[l] || ESC.ligaNom(l)]), s.liga);
    opts($1("#ieqEq"), equipos.map((r) => [r.id, r.eq]), s.eq);
    opts($1("#ieqFase"), (fases && fases.length ? fases : FASES), s.fase);
    document.querySelectorAll("#ieqVer [data-v]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.v === s.ver)));
    if ($1("#ieqPara") && document.activeElement !== $1("#ieqPara")) $1("#ieqPara").value = s.para || "";
    const mm = minMinEq(s); if ($1("#ieqMin")) $1("#ieqMin").value = String(Math.min(mm, 1500)); if ($1("#ieqMinN") && document.activeElement !== $1("#ieqMinN")) $1("#ieqMinN").value = String(mm);
    cargarNota();
  }
  function cargarNota() { const { s } = estado(), n = lsGet()[claveNota(s)] || {}; if ($1("#ieqNota")) $1("#ieqNota").value = n.raw || ""; if ($1("#ieqNotaFin")) $1("#ieqNotaFin").value = n.fin || ""; if ($1("#ieqNotaMsg")) $1("#ieqNotaMsg").textContent = n.fin ? "Texto en tono Kerno guardado para este equipo y temporada." : ""; }
  function guardarNota() { const { s } = estado(), o = lsGet(); o[claveNota(s)] = { raw: $1("#ieqNota").value, fin: $1("#ieqNotaFin").value }; lsSet(o); }
  let construido = false, TOK = 0, ULT = null, PDF = null;
  function construir() {
    if (construido || !$1("#ieqPages")) return; construido = true;
    const cambia = () => { guardar(); pintarControles(); pintar(); };
    $1("#ieqTemp").onchange = (e) => { st.ieq.temp = e.target.value; cambia(); };
    $1("#ieqLiga").onchange = (e) => { st.ieq.liga = e.target.value; st.ieq.eq = null; cambia(); };
    $1("#ieqEq").onchange = (e) => { st.ieq.eq = e.target.value; cambia(); };
    $1("#ieqFase").onchange = (e) => { st.ieq.fase = e.target.value; cambia(); };
    let tMin = null; const fijaMin = (v, ya) => { st.ieq.minMin = Math.max(0, Math.min(4000, Math.round(+v || 0))); clearTimeout(tMin); if (ya) cambia(); else { pintarControles(); notaMin(null); tMin = setTimeout(cambia, 450); } };
    if ($1("#ieqMin")) { $1("#ieqMin").oninput = (e) => fijaMin(e.target.value, false); $1("#ieqMinN").onchange = (e) => fijaMin(e.target.value, true); }
    if ($1("#ieqVer")) $1("#ieqVer").onclick = (e) => { const b = e.target.closest("[data-v]"); if (!b) return; st.ieq.ver = b.dataset.v; cambia(); };
    let tp = null; $1("#ieqPara").oninput = (e) => { st.ieq.para = e.target.value.slice(0, 60); guardar(); clearTimeout(tp); tp = setTimeout(pintar, 600); };
    $1("#ieqBus").oninput = () => { const q = normQ($1("#ieqBus").value).trim().split(/\s+/).filter(Boolean), box = $1("#ieqBusS"); if (!q.length || !EVX) { box.hidden = true; return; }
      const vis = new Map(); EVX.F.filter((r) => r.f === "regular" && q.every((p) => normQ(r.eq).includes(p))).forEach((r) => { const k = `${r.t}|${r.liga}|${r.id}`; if (!vis.has(k)) vis.set(k, r); });
      const res = [...vis.values()].sort((a, b) => b.t.localeCompare(a.t) || String(a.eq).localeCompare(String(b.eq))).slice(0, 24);
      box.innerHTML = res.map((r) => `<button type="button" data-k="${E(`${r.t}|${r.liga}|${r.id}`)}"><span>${E(r.eq)}</span><small>${E(LC[r.liga] || ESC.ligaCorto(r.liga))} ${E(r.t)}</small></button>`).join("") || `<span class="note" style="padding:6px">Sin resultados.</span>`; box.hidden = false; };
    $1("#ieqBusS").onclick = (e) => { const b = e.target.closest("[data-k]"); if (!b) return; const [t, l, id] = b.dataset.k.split("|"); $1("#ieqBusS").hidden = true; $1("#ieqBus").value = ""; Object.assign(st.ieq, { temp: t, liga: l, eq: id, fase: "regular" }); cambia(); };
    let tm = null; const rep = () => { clearTimeout(tm); tm = setTimeout(pintar, 600); };
    $1("#ieqNota").addEventListener("input", () => { guardarNota(); rep(); });
    $1("#ieqNotaFin").addEventListener("input", () => { guardarNota(); rep(); });
    $1("#ieqNotaBorrar").onclick = () => { $1("#ieqNota").value = ""; $1("#ieqNotaFin").value = ""; guardarNota(); $1("#ieqNotaMsg").textContent = ""; pintar(); };
    $1("#ieqRedactar").onclick = redactar;
    $1("#ieqPdf").onclick = descargar; $1("#ieqHtml").onclick = exportarHtml; $1("#ieqAbrir").onclick = abrir;
    addEventListener("resize", () => { if (st.tab === "informeq") escalar(); });
  }
  // texto bajo el control: cuántos jugadores entran con el mínimo elegido
  function notaMin(c) { const el = $1("#ieqMinNota"); if (!el) return; const mm = minMinEq(st.ieq);
    const n = c ? (mm ? `Entran los jugadores con <b>${mm}'</b> o más: ${c.jug.length} de ${c.nTodos}.` : `Sin mínimo: entran todos los jugadores con minutos (${c.nTodos}).`) : (mm ? `Entran los jugadores con <b>${mm}'</b> o más.` : "Sin mínimo: entran todos los jugadores con minutos.");
    el.innerHTML = `${n} Minutos jugados en la temporada y la fase elegidas. Se aplica a lo individual: jugadores, rotación, reparto de puntos, ataque y defensa, quintetos, parejas y red de pases. Las cifras del equipo no cambian.`; }
  function escalar() { const box = $1("#ieqPages"); if (!box) return; const w = box.clientWidth || IF_W; box.style.setProperty("--k", Math.min(1, (w - 2) / IF_W).toFixed(4)); }
  async function pintar() {
    const box = $1("#ieqPages"); if (!box || !META) return;
    construir();
    const tok = ++TOK; box.classList.add("cargando"); $1("#ieqMsg").textContent = ""; PDF = null; alternativas(false);
    try { await ev(); } catch (e) { if (tok === TOK) { box.classList.remove("cargando"); box.innerHTML = `<p class="note">No se pudieron cargar los datos de equipos (${E(e.message || e)}).</p>`; } return; }
    pintarControles();
    const { s } = estado(); if (!s.eq) { box.classList.remove("cargando"); box.innerHTML = `<p class="note">No hay equipos con datos en esa competición y temporada.</p>`; return; }
    await (typeof cargarSim === "function" ? cargarSim().catch(() => null) : null);
    let c; try { c = await contexto(s); } catch (e) { if (tok === TOK) { box.classList.remove("cargando"); box.innerHTML = `<p class="note">No se pudo preparar el informe (${E(e.message || e)}).</p>`; } console.error(e); return; }
    if (tok !== TOK) return;
    if (c.error) { box.classList.remove("cargando"); box.innerHTML = `<p class="note">Este equipo no tiene datos en la fase elegida.</p>`; return; }
    c.fecha = new Date().toLocaleDateString("es-ES", { day: "numeric", month: "long", year: "numeric" });
    let hojas; try { hojas = paginas(c); } catch (e) { box.classList.remove("cargando"); box.innerHTML = `<p class="note">No se pudo componer el informe (${E(e.message || e)}).</p>`; console.error(e); return; }
    box.innerHTML = hojas.map((h) => `<div class="ifwrap">${h}</div>`).join("");
    box.classList.remove("cargando"); escalar();
    ULT = { nom: c.nombre, temp: c.t, ver: s.ver, ctx: contextoTexto(c) }; notaMin(c);
    $1("#ieqResumen").textContent = `${hojas.length} páginas A4 · ${c.nombre} · ${c.t}${c.T ? "" : " · sin datos de quintetos en esta liga y temporada: sin páginas de rotación, quintetos y conexiones"}`;
  }
  function contextoTexto(c) {
    const r = c.r, ent = c.ent.map((e) => e.n).join(", después ");
    return [`Equipo: ${c.nombre} (${c.ligaNom} ${c.t}, ${FNOM[c.s.fase]}). Entrenador: ${ent || "s/d"}.`,
      c.bal ? `Balance: ${c.bal.w}-${c.bal.l}${c.rkW ? `, ${c.rkW}.º de ${c.nW}` : ""}.` : "",
      ok(r.net) ? `Diferencia de puntos: ${SG(r.net, 1)} por 100 posesiones (${c.rkN}.º de ${c.n}); anota ${N(r.ortg, 1)} y encaja ${N(r.drtg, 1)}.` : "",
      c.SL != null ? `Nivel de la plantilla frente a las de su liga: ${ESC.txt(c.SL)} en escala ±100 (0 = plantilla media de su liga)${c.rkPl ? `, ${c.rkPl}.ª de ${c.nPl}` : ""}.` : "",
      c.eu ? `Estilo: ${c.eu.etiqueta}.` : "",
      c.fuertes.length ? `Puntos fuertes en su liga: ${c.fuertes.map((m) => `${m.nm.toLowerCase()} (percentil ${Math.round(m.p)})`).join(", ")}.` : "",
      c.debiles.length ? `A mejorar: ${c.debiles.map((m) => `${m.nm.toLowerCase()} (percentil ${Math.round(m.p)})`).join(", ")}.` : ""].filter(Boolean).join("\n");
  }
  // nota del analista → texto en tono Kerno (Claude, a través de la página principal, con el mismo permiso que la lectura de fichaje)
  let SREQ = 0; const SPEND = new Map();
  addEventListener("message", (e) => { const r = e.data && e.data.cernoSampleRes; if (!r || !SPEND.has(r.id)) return; SPEND.get(r.id)(r); SPEND.delete(r.id); });
  function pedirClaude(prompt) {
    if (window.parent === window) return (async () => { try { const sm = window.claude && window.claude.use ? await window.claude.use("sample") : null; if (!sm) return { error: "unavailable" }; const r = await sm(prompt, { modelTier: "default" }); return { text: r && r.text }; } catch (er) { return { error: (er && er.code) || String((er && er.message) || er) }; } })();
    return new Promise((okk) => { const id = `ieq-${++SREQ}`; SPEND.set(id, okk); setTimeout(() => { if (SPEND.has(id)) { SPEND.delete(id); okk({ error: "sin_respuesta" }); } }, 240000);
      try { window.parent.postMessage({ cernoSample: { id, prompt } }, "*"); } catch (er) { SPEND.delete(id); okk({ error: String(er.message || er) }); } });
  }
  const SERR = { unavailable: "este visor no permite usar Claude desde la página", not_granted: "no se ha dado permiso para usar Claude", rate_limited: "demasiadas peticiones; inténtalo en un momento", sin_respuesta: "la página principal no respondió" };
  async function redactar() {
    const raw = $1("#ieqNota").value.trim(), msg = $1("#ieqNotaMsg"), btn = $1("#ieqRedactar");
    if (!raw) { msg.textContent = "Escribe primero tu valoración."; return; }
    const prompt = `Eres redactor de Kerno Analytics, socio independiente de inteligencia de talento para el deporte de élite, empezando por el baloncesto. Reescribe la valoración del analista para el apartado «Valoración Kerno» de un informe sobre el estado de un equipo.

Voz de marca: exacta, franca, tranquila; como un analista senior que ha visto mucho baloncesto. Empieza por la conclusión. Lenguaje de baloncesto, sin jerga de modelos. Sin superlativos (nada de «el mejor», «élite», «increíble», «brutal»), sin «revolucionar», «garantizado» ni «magia». Respeto por jugadores y entrenadores.

Reglas estrictas:
- Español de España. Tercera persona («en Kerno vemos», «el equipo»…).
- No inventes datos, cifras, lesiones, rasgos ni hechos que no estén en la nota o en el contexto. Puedes usar solo las cifras del contexto, tal cual.
- Entre 70 y 130 palabras, en 2 párrafos breves. Sin títulos, sin viñetas, sin comillas, sin firma.
- Devuelve solo el texto final.

Contexto del equipo (datos del informe):
${ULT && ULT.ctx ? ULT.ctx : ""}

Valoración del analista:
${raw}`;
    btn.disabled = true; msg.textContent = "Redactando en tono Kerno… (la primera vez Claude pide permiso)";
    const r = await pedirClaude(prompt); btn.disabled = false;
    if (r && r.text) { $1("#ieqNotaFin").value = r.text.trim(); guardarNota(); msg.textContent = "Listo. Revisa el texto: es el que entra en el informe."; pintar(); }
    else msg.textContent = `No se pudo redactar (${SERR[r && r.error] || (r && r.error) || "error"}). El informe usará tu valoración tal cual.`;
  }

  // ------------------------------------------------------------------------------------------- 5. PDF, HTML imprimible y pestaña nueva (mismo motor que la lectura de fichaje)
  const cssHojas = () => { const v3 = document.getElementById("cerno-informe-v3"); return INF_CSS + "\n" + (v3 ? v3.textContent : "") + "\n" + CSSQ; };
  const nombre = (ext) => `Kerno Analytics - Informe de equipo ${ULT ? ULT.nom : ""} ${ULT ? ULT.temp : ""}.${ext}`.replace(/[\\/:*?"<>|]/g, " ").replace(/\s+/g, " ");
  function alternativas(m) { const b = $1("#ieqAlt"); if (b) b.classList.toggle("realce", !!m); if (!m) ifQuitarEnlace("ieqAlt"); }
  async function rasterFO(el, k) {
    const fuentes = await ifFuentes(), xs = new XMLSerializer().serializeToString(el);
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${IF_W}" height="${IF_H}"><foreignObject x="0" y="0" width="${IF_W}" height="${IF_H}"><div xmlns="http://www.w3.org/1999/xhtml" style="width:${IF_W}px;height:${IF_H}px"><style>${(fuentes + "\n" + cssHojas()).replace(/]]>/g, "")}</style>${xs}</div></foreignObject></svg>`;
    const img = new Image(); img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg); await img.decode();
    const cv = document.createElement("canvas"); cv.width = Math.round(IF_W * k); cv.height = Math.round(IF_H * k);
    const g = cv.getContext("2d"); g.fillStyle = "#F3F4F0"; g.fillRect(0, 0, cv.width, cv.height); g.drawImage(img, 0, 0, cv.width, cv.height); return cv;
  }
  async function generarPdf(msg) {
    const hojas = [...document.querySelectorAll("#ieqPages .ifsheet")]; if (!hojas.length) throw new Error("no hay informe");
    const imgs = await ifRasterizarHojas(hojas, msg, cssHojas());
    return ifPdf(imgs, { title: `Kerno Analytics · Informe de equipo · ${ULT ? ULT.nom : ""}`, author: "Kerno Analytics", subject: "Informe de equipo" });
  }
  function htmlImprimible() {
    const hojas = [...document.querySelectorAll("#ieqPages .ifsheet")].map((h) => h.outerHTML).join("\n"), tit = `Kerno Analytics · Informe de equipo · ${ULT ? ULT.nom : ""}`;
    return `<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${E(tit)}</title>
<style>${IFFONT || ""}
${cssHojas()}
@page { size: A4 portrait; margin: 0; }
html, body { margin: 0; background: #8F9993; }
.ifbarra { position: sticky; top: 0; z-index: 5; display: flex; gap: 14px; align-items: center; justify-content: center; padding: 10px 16px; background: #0F2E25; color: #F3F4F0; font: 500 13px Mona Sans, system-ui, sans-serif; }
.ifbarra button { font: 700 11px Mona Sans, sans-serif; letter-spacing: .16em; text-transform: uppercase; padding: 8px 14px; border-radius: 4px; border: 0; background: #F3F4F0; color: #0C1210; cursor: pointer; }
.ifdoc { display: grid; justify-content: center; gap: 18px; padding: 22px 0 40px; }
.ifdoc .ifsheet { box-shadow: 0 10px 30px -12px rgba(12, 18, 16,.45); }
.ifbarra { flex-wrap: wrap; text-align: center; }
@media print { .ifdoc .ifsheet { zoom: 1 !important; } }
@media print { html, body { background: #F3F4F0; } .ifbarra { display: none; } .ifdoc { display: block; padding: 0; } .ifdoc .ifsheet { box-shadow: none; break-after: page; page-break-after: always; -webkit-print-color-adjust: exact; print-color-adjust: exact; } }
</style></head><body><div class="ifbarra"><span>Para el PDF: Imprimir y «Guardar como PDF» · A4 · márgenes: ninguno · gráficos de fondo: sí</span><button onclick="print()">Imprimir</button></div><div class="ifdoc">${hojas}</div><script>(function(){function z(){var k=Math.min(1,(window.innerWidth-16)/794);document.querySelectorAll(".ifdoc .ifsheet").forEach(function(s){s.style.zoom=k<1?k:"";});}addEventListener("resize",z);z();})();<\/script></body></html>`;
  }
  async function descargar() {
    const btn = $1("#ieqPdf"), msg = $1("#ieqMsg"); if (btn.disabled) return; btn.disabled = true; msg.textContent = "Preparando el PDF…";
    try {
      const blob = await generarPdf(msg), bytes = await blob.arrayBuffer(); PDF = bytes; window.__ieqUltimoPdf = blob;
      msg.textContent = "PDF listo. Confirma la descarga en el aviso de Claude…";
      const r = await ifShell("guardar", nombre("pdf"), bytes.slice(0), "application/pdf");
      if (r.ok) { msg.textContent = `Descargado: «${nombre("pdf")}».`; alternativas(false); return; }
      if (r.error === "declined") { msg.textContent = IF_ERR.declined; alternativas(true); return; }
      alternativas(true); ifEnlace("ieqAlt", blob, nombre("pdf")); msg.textContent = `No se pudo guardar el PDF aquí (${ifErr(r.error)}). Toca «Abrir el PDF generado» o usa una de las otras opciones.`;
    } catch (e) { msg.textContent = `No se pudo generar el PDF (${e && e.message ? e.message : e}). Usa el HTML imprimible.`; alternativas(true); }
    finally { btn.disabled = false; }
  }
  async function exportarHtml() {
    const msg = $1("#ieqMsg"); if (!document.querySelector("#ieqPages .ifsheet")) return; msg.textContent = "Preparando el HTML imprimible…"; await ifFuentes();
    const r = await ifShell("guardar", nombre("html"), htmlImprimible(), "text/html");
    msg.textContent = r.ok ? `Descargado: «${nombre("html")}». Ábrelo en el navegador y pulsa «Imprimir» y «Guardar como PDF» (A4, sin márgenes).` : r.error === "declined" ? IF_ERR.declined : `No se pudo descargar el HTML (${ifErr(r.error)}). Prueba «Abrir en pestaña nueva».`;
  }
  async function abrir() {
    const msg = $1("#ieqMsg"), ab = $1("#ieqAbrir"); ab.disabled = true;
    try { if (!PDF) { msg.textContent = "Preparando el PDF…"; const blob = await generarPdf(msg); PDF = await blob.arrayBuffer(); window.__ieqUltimoPdf = blob; }
      const r = await ifShell("abrir", nombre("pdf"), PDF.slice(0), "application/pdf", 20000);
      msg.textContent = r.ok ? "Abierto en una pestaña nueva: guárdalo o imprímelo desde el visor de PDF." : `No se pudo abrir la pestaña (${ifErr(r.error)}). Usa «Descargar PDF» o «HTML imprimible».`;
    } catch (e) { msg.textContent = `No se pudo preparar el PDF (${e && e.message ? e.message : e}).`; } finally { ab.disabled = false; }
  }

  // ------------------------------------------------------------------------------------------- 6. estilos propios (pantalla, PDF e HTML imprimible)
  const CSSQ = `
#ieqVer{display:flex;gap:0;border:1px solid var(--line-2);border-radius:2px;overflow:hidden}#ieqVer button{flex:1;font:600 12px var(--f-body);letter-spacing:.04em;padding:7px 8px;border:0;background:transparent;color:var(--muted);cursor:pointer}#ieqVer button[aria-pressed="true"]{background:var(--btn-bg);color:var(--btn-ink)}
#ieqNotaBox{display:grid;gap:6px}#ieqNotaBox textarea,#ieqPara{width:100%;font:400 13px/1.45 var(--f-body);color:var(--ink);background:var(--surface);border:1px solid var(--line-2);border-radius:2px;padding:8px 10px;resize:vertical}
#ieqPages{--k:1;display:grid;gap:18px;justify-items:center;padding:18px 0 30px;border-radius:4px;background:var(--surface-3,#E3E7E2);min-height:300px;transition:opacity .2s}#ieqPages.cargando{opacity:.45}
.ifsheet.ieq .ax{font:500 6.8px "Geist Mono",monospace;fill:#56625C}.ifsheet.ieq .ax.on{fill:#0C1210;font-weight:700}.ifsheet.ieq .pv{font:600 7.4px "Geist Mono",monospace;fill:#0C1210}
.ifsheet.ieq .nm{font:500 9.4px "Mona Sans",sans-serif;fill:#0C1210}.ifsheet.ieq .nm .sb{font:500 7.4px "Geist Mono",monospace;fill:#707B75}.ifsheet.ieq .vv{font:600 8.6px "Geist Mono",monospace;fill:#0C1210}.ifsheet.ieq .hlr{fill:#DCE7E2}
.ifsheet.ieq .pn{font:620 8.6px "Mona Sans",sans-serif;fill:#0C1210}.ifsheet.ieq .pp{font:600 8px "Geist Mono",monospace;fill:#F3F4F0}
.ieq-pb,.ieq-tira{display:block}.ieq-dv,.ieq-mn,.ieq-pista,.ieq-red,.ieq-ev,.ieq-zn,.ieq-pu,.ieq-map{display:block;max-width:100%;height:auto}
.r3t.ieq-m td{padding:3px 6px 3px 0}.r3t.ieq-m th{padding-right:10px}.r3t.ieq-m td small{display:inline;margin-left:5px}.r3t.ieq-m td.num small{display:block;margin:0}.r3t b.neu{color:var(--vi)}.r3t b.up{color:var(--up)}.r3t b.dn{color:var(--dn)}
.r3t.ieq-q td{padding:3.4px 6px 3.4px 0}.r3t.ieq-q td.hc{text-align:center;padding:3.4px 2px;font-size:9.4px;border-right:1.5px solid #F3F4F0}
.r3t.ieq-j td{padding:4px 6px 4px 0;font-size:9.8px}.r3t.ieq-us td:first-child b{display:block;max-width:330px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.r3t.ieq-us td{padding:4px 6px 4px 0}.r3t.ieq-j th{white-space:nowrap}
.ieq-tr{display:grid;grid-template-columns:200px 300px 1fr;gap:12px;align-items:center;padding:6px 0;border-bottom:.5px solid #B2BAB5}.ieq-tr b{display:block;font:620 11px "Mona Sans",sans-serif}.ieq-tr small{display:block;font-size:8.6px;color:#56625C;line-height:1.3;margin-top:1px}
.ieq-trv{text-align:right}.ieq-trv b{font:620 18px/1 "Mona Sans",sans-serif!important}.ieq-trv b.up{color:#2B6FBF}.ieq-trv b.dn{color:#D35C2A}.ieq-trv b.neu{color:#6550CC}
.ieq-tiles{display:grid;grid-template-columns:repeat(4,1fr);border-top:1.2px solid #0F2E25;border-bottom:.5px solid #B2BAB5}.ieq-tiles>div{padding:9px 12px 9px 0;margin-right:12px;border-right:.5px solid #B2BAB5}.ieq-tiles>div:last-child{border:0;margin:0}
.ieq-tiles span{display:block;font:500 7.2px "Geist Mono",monospace;letter-spacing:.08em;text-transform:uppercase;color:#56625C}.ieq-tiles b{display:block;font:620 30px/1.05 "Mona Sans",sans-serif;letter-spacing:-.02em;margin:5px 0 3px}.ieq-tiles small{display:block;font-size:8.8px;color:#56625C}
.ieq-tiles .idx{border-left:2pt solid #0F2E25;padding-left:10px}
.ieq-fac{display:grid;grid-template-columns:1fr 120px 26px;gap:8px;align-items:center;padding:4px 0;border-bottom:.5px solid #CFD5D0;font-size:10px}.ieq-fac b{font:600 10px "Geist Mono",monospace;text-align:right}.ieq-fac b.up{color:#2B6FBF}.ieq-fac b.dn{color:#D35C2A}
.ieq-q5{font:620 12.6px/1.35 "Mona Sans",sans-serif;margin:2px 0 6px!important;padding:8px 10px;border-left:2pt solid #0F2E25;background:#E3E7E2}
.r3yo.ieq-kv{grid-template-columns:repeat(4,1fr)}.r3yo.ieq-kv b{font-size:10.6px}
.ieq-ley{display:flex;flex-wrap:wrap;gap:4px 12px;margin:4px 0 0!important;font-size:8.4px;color:#3F4B45}.ieq-ley span{display:inline-flex;align-items:center;gap:4px}.ieq-ley i{width:9px;height:9px;display:inline-block}
.ieq-red3{display:grid;grid-template-columns:1fr 1fr 1.3fr;gap:18px}.ieq-red3 .r3rank li{grid-template-columns:16px 1fr auto}
.ieq-tl{position:relative;height:12px;background:#E3E7E2;margin:4px 0 2px}.ieq-tl i{position:absolute;top:0;bottom:0;display:block;border-right:1px solid #F3F4F0}.ieq-tlax{display:flex;justify-content:space-between;font:500 7px "Geist Mono",monospace;color:#56625C;margin-bottom:6px}
.ieq-ents{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}.ieq-ents>div{border-top:.9px solid #0F2E25;padding-top:6px;display:grid;gap:2px}.ieq-ents b{font:620 12px "Mona Sans",sans-serif}.ieq-ents small{font-size:8.4px;color:#56625C}
.ieq-ents span{display:flex;justify-content:space-between;font:500 9.6px "Geist Mono",monospace;border-bottom:.5px solid #CFD5D0;padding:1.5px 0}.ieq-ents em{font:400 9.4px "Mona Sans",sans-serif;font-style:normal;color:#56625C}
.ieq-cards{display:grid;grid-template-columns:repeat(3,1fr);gap:9px 14px}.ieq-card{border-top:.9px solid #0F2E25;padding-top:5px}.ieq-card .h{display:flex;align-items:center}.ieq-card .h b{font:620 11.2px "Mona Sans",sans-serif}.ieq-card>small{display:block;font-size:8.2px;color:#56625C;margin:1px 0 4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ieq-card .k{display:grid;grid-template-columns:1.4fr repeat(4,1fr);gap:4px;align-items:end}.ieq-card .k span{font:600 10px "Geist Mono",monospace;display:grid}.ieq-card .k em{font:500 6.4px "Geist Mono",monospace;font-style:normal;letter-spacing:.06em;text-transform:uppercase;color:#56625C}.ieq-card .k b.up{color:#2B6FBF}.ieq-card .k b.dn{color:#D35C2A}
.ieq-rs{display:grid;grid-template-columns:1fr auto 58px;gap:6px;align-items:center;padding:2px 0;border-bottom:.5px solid #B2BAB5}.ieq-rs b{display:block;font:620 10.4px "Mona Sans",sans-serif}.ieq-rs small{display:block;font-size:8.2px;color:#56625C;line-height:1.25}
.ieq-rs .ieq-trv b{font-size:14px!important}.ieq-entc:not(.r3cols){display:grid;gap:12px}.r3t.ieq-tray td{padding:3.4px 6px 3.4px 0;font-size:9.4px}.ifsheet .ieq-lim{border-left:2pt solid #0F2E25;padding-left:10px;font-size:10.4px!important}
.r3mini.ieq-reb b.up{color:#2B6FBF}.r3mini.ieq-reb b.dn{color:#D35C2A}
.ifsheet.ieq .r3inkheroE p{font-size:11.6px!important}
/* v1.4 · rotación compacta, composición de la plantilla, tiempos muertos y stops */
.r3t.ieq-q.cmp td{padding:1.2px 5px 1.2px 0;font-size:8.8px}.r3t.ieq-q.cmp td.hc{padding:1.2px 2px;font-size:8.4px}.r3t.ieq-q.cmp th{padding-bottom:2px}.r3t.ieq-q.cmp .r3rol{font-size:7.6px;padding:1px 4px}
.ieq-b100,.ieq-ad{display:block;max-width:100%;height:auto}
.r3mini.ieq-comp{grid-template-columns:repeat(3,1fr);margin-bottom:6px}.r3mini.ieq-comp b.up{color:#2B6FBF}.r3mini.ieq-comp b.dn{color:#D35C2A}
.ifsheet .ieq-compt{font-size:10.4px;line-height:1.45;margin:4px 0 2px!important}
.ieq-compb .ieq-ley,.ieq-stops .ieq-ley{margin:0 0 5px!important}
.ieq-ley i{border-radius:1px}.ieq-ley.est{margin-top:2px!important}
.ifsheet .ieq-h3s{font:620 13px/1.2 "Mona Sans",sans-serif!important;margin:2px 0 0!important}
.r3kp.big.ieq-tmk b{font-size:24px}
.ifsheet.cmp .ieq-tr{padding:3px 0}.ieq-ley .pre{color:#56625C}`;
  const stq = document.createElement("style"); stq.id = "cerno-informe-equipo"; stq.textContent = CSSQ; document.head.appendChild(stq);

  window.CernoInformeEquipo = { version: "1.5", pintar, escalar, paginas, contexto };
})();
