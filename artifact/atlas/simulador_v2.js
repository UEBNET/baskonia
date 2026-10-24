/* Simulador de encaje v2 — motor en el navegador.
 * Port de bbfit.simulador.simular (Python, la referencia). Mismas ecuaciones y mismos datos (atlas/simulador/*.json,
 * generados por bbfit/sim_exportar.py); los números aleatorios no son los de numpy, así que Python y JS coinciden en
 * distribución (paridad comprobada en las medias dentro del error Monte Carlo), no bit a bit.
 * Flujo de cada iteración: nivel latente traducido al destino → adaptación → minutos y rol endógenos (Plackett-Luce con
 * las tendencias del entrenador) → uso (suma fija) y curva uso-eficiencia → calidad de compañeros → ruido personal →
 * ritmo del club. Salidas: roles, minutos, producción /100 y por partido con intervalos, Fit, impacto en el Net,
 * quintetos, ADAPT% y curva, avisos. El usuario no introduce minutos.
 */
(function (raiz) {
  "use strict";
  const ROLES = ["RESIDUAL", "PROFUNDIDAD", "ROTACION", "TITULAR", "GO_TO_GUY"];
  let D = null;           // { meta, jug: Map(id → registro), clubes: [..], porClub: Map }

  // ------------------------------------------------------------------ utilidades
  const fin = (x) => typeof x === "number" && isFinite(x);
  const num = (x, d = NaN) => (fin(x) ? x : d);
  function cols(d) { return d.filas.map((f) => Object.fromEntries(d.columnas.map((c, i) => [c, f[i]]))); }
  function crc(s) { let h = 2166136261 >>> 0; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619) >>> 0; } return h; }
  function rngDe(semilla) {           // mulberry32 + Box-Muller
    let a = semilla >>> 0, sobra = null;
    const u = () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
    const n = () => { if (sobra !== null) { const s = sobra; sobra = null; return s; } let x, y, r; do { x = 2 * u() - 1; y = 2 * u() - 1; r = x * x + y * y; } while (r >= 1 || r === 0); const f = Math.sqrt(-2 * Math.log(r) / r); sobra = y * f; return x * f; };
    const g = () => -Math.log(-Math.log(Math.max(u(), 1e-300)));
    return { u, n, g, int: () => Math.floor(u() * 2147483647) };
  }
  const TR = (x, t) => { if (!fin(x)) return NaN; if (t === "raiz") return Math.sqrt(Math.max(0, x)); if (t === "log1") return Math.log1p(Math.max(0, x)); if (t === "proporcion") return Math.asin(Math.sqrt(Math.min(100, Math.max(0, x)) / 100)); return x; };
  const TRinv = (y, t) => { if (!fin(y)) return NaN; if (t === "raiz") return Math.max(0, y) ** 2; if (t === "log1") return Math.expm1(Math.max(0, y)); if (t === "proporcion") return 100 * Math.sin(Math.min(Math.PI / 2, Math.max(0, y))) ** 2; return y; };
  const logit = (p, lo = 0.02, hi = 0.98) => { const q = Math.min(hi, Math.max(lo, p)); return Math.log(q / (1 - q)); };
  function cuantil(arr, a) { const v = arr.filter(fin).sort((x, y) => x - y); if (!v.length) return null; const h = (v.length - 1) * a, i = Math.floor(h); return i + 1 < v.length ? v[i] + (h - i) * (v[i + 1] - v[i]) : v[i]; }
  const media = (arr) => { const v = arr.filter(fin); return v.length ? v.reduce((s, x) => s + x, 0) / v.length : null; };
  function resumen(arr, niveles) { const d = { media: media(arr), mediana: cuantil(arr, 0.5) }; niveles.forEach((a) => { const k = Math.round(a * 100); d["lo" + k] = cuantil(arr, (1 - a) / 2); d["hi" + k] = cuantil(arr, 1 - (1 - a) / 2); }); return d; }
  function tramo(edad) { if (!fin(edad)) return "s/d"; for (const [lo, hi, n] of [[-1, 23, "≤23"], [24, 26, "24-26"], [27, 29, "27-29"], [30, 32, "30-32"], [33, 99, "33+"]]) if (lo <= edad && edad <= hi) return n; return "s/d"; }
  function entropiaNorm(w) { const v = w.filter((x) => fin(x) && x > 0); if (v.length < 2) return 0; const s = v.reduce((a, b) => a + b, 0); let h = 0; v.forEach((x) => { const p = x / s; h -= p * Math.log2(p); }); return h / Math.log2(v.length); }
  function js(p, q) { if (!p || !q || p.some((x) => !fin(x)) || q.some((x) => !fin(x))) return NaN; const sp = p.reduce((a, b) => a + b, 0), sq = q.reduce((a, b) => a + b, 0); if (sp <= 0 || sq <= 0) return NaN; const P = p.map((x) => x / sp), Q = q.map((x) => x / sq), M = P.map((x, i) => (x + Q[i]) / 2); const kl = (a, b) => a.reduce((s, x, i) => s + (x > 0 ? x * Math.log2(Math.max(x, 1e-12) / Math.max(b[i], 1e-12)) : 0), 0); return 0.5 * kl(P, M) + 0.5 * kl(Q, M); }

  // ------------------------------------------------------------------ carga
  function cargar(meta, jugadores, clubes) {
    const jug = new Map(); cols(jugadores).forEach((r) => jug.set(r.id, r));
    const cl = cols(clubes);
    const porClub = new Map(cl.map((c) => [`${c.liga}|${c.team}|${c.temporada}`, c]));
    const porPersona = new Map(); jug.forEach((r) => { if (!porPersona.has(r.persona)) porPersona.set(r.persona, []); porPersona.get(r.persona).push(r); });
    D = { meta, jug, clubes: cl, porClub, porPersona };
    return D;
  }
  const minPartido = (liga) => num(D.meta.min_partido[liga], D.meta.min_partido.defecto);
  const baseDe = (club) => D.meta.bases[club.base];
  const ligaBase = (base, liga) => (D.meta.bases[base].ligas || {})[liga];

  // ------------------------------------------------------------------ 1. traducción
  function traducir(rec, ligaD, base, metricas, z1, z2, rng, n) {
    const out = {}, LB = ligaBase(base, ligaD), pos = ["E", "A", "I"].includes(rec.pos3) ? rec.pos3 : "A";
    metricas.forEach((m) => {
      const k = D.meta.metricas.indexOf(m), K = LB && LB.metricas[m];
      const th = rec.th ? rec.th[k] : NaN; let sd = rec.sd ? rec.sd[k] : NaN;
      if (!K || !fin(th)) { out[m] = z1 ? new Array(n).fill(NaN) : NaN; return; }
      if (!fin(sd)) sd = 0.5;
      const der = num((D.meta.deriva[m] || {})[tramo(rec.edad)], 0), [dd, vd] = K.nodo, mu = K.mu[pos], tau = K.tau[pos];
      const tf = D.meta.transf[m];
      if (!z1) { out[m] = TRinv(mu + tau * ((th + der - dd) / K.s), tf); out["_" + m + "_z"] = (th + der - dd) / K.s; return; }
      const v = new Array(n);
      for (let s = 0; s < n; s++) { const zd = (th + der + sd * z1[s] - (dd + Math.sqrt(Math.max(vd, 0)) * z2[s])) / K.s + Math.sqrt(Math.max(K.psi, 0)) * rng.n(); v[s] = TRinv(mu + tau * zd, tf); }
      out[m] = v;
    });
    return out;
  }
  function ruido(m, ligaD, base, valores, expo, rng) {
    const K = ligaBase(base, ligaD).metricas[m], tf = D.meta.transf[m];
    if (!K || !fin(K.sigma2)) return valores;
    return valores.map((v, s) => TRinv(TR(v, tf) + rng.n() * Math.sqrt(K.sigma2 / Math.max(expo[s], 1)), tf));
  }

  // ------------------------------------------------------------------ 2. adaptación (fase 7)
  function grupoNac(nac, lo, ld) {
    const A = D.meta.adaptacion, po = A.paises_liga[lo], pd = A.paises_liga[ld], usO = po === "US", usD = pd === "US";
    if (usO && usD) return "intra_EEUU"; if (usD) return "hacia_EEUU";
    const nats = nac ? String(nac).split("/").filter(Boolean) : [];
    if (!nats.length) return "desconocido";
    if (usO) return nats.includes("US") ? "EEUU_a_Europa" : "otro_desde_EEUU";
    if (po != null && po === pd && po !== "EUR") return nats.includes(po) ? "nacional_mismo_pais" : "extranjero_mismo_pais";
    if (nats.some((n) => A.paises_europeos.includes(n))) return "europeo_cambia_liga";
    return "extranjero_cambia_pais";
  }
  let PRI = null;
  function escalonDe(liga) { const E = D.meta.adaptacion.escalones || {}; for (const k in E) if (E[k].includes(liga)) return k; return null; }
  function prior(lo, ld, gr, p3, metrica) {
    const A = D.meta.adaptacion, def = A.defecto;
    const base = { delta_media: def[0], delta_sd: def[1], kappa_media: def[2], kappa_sd: def[3], n: 0, nivel_fallback: "sin_datos",
      delta_temporada_media: def[0], delta_temporada_sd: def[1], D_forma_media: NaN, kappa_forma_media: NaN, partidos_50: NaN, partidos_90: NaN };
    if (!A.priors) return base;
    if (!PRI) { PRI = new Map(); cols(A.priors).forEach((r) => { const k = [r.metrica, r.nivel, r.liga_origen, r.liga_destino, r.grupo_nacionalidad, r.pos3, r.nivel.startsWith("escalon") ? r.escalon_destino : ""].join("|"); if (!PRI.has(k)) PRI.set(k, r); }); }
    const C = "*", esc = escalonDe(ld) || C;
    const claves = [["celda", lo, ld, gr, p3], ["par_grupo", lo, ld, gr, C], ["par", lo, ld, C, C], ["escalon_grupo", C, C, gr, C], ["escalon", C, C, C, C], ["global_grupo", C, C, gr, C], ["global", C, C, C, C]];
    for (const [nv, a, b, c, d] of claves) {
      const r = PRI.get([metrica, nv, a, b, c, d, nv.startsWith("escalon") ? esc : ""].join("|"));
      if (!r) continue;
      if (r.n < A.n_min && nv !== "global") continue;
      const o = { ...r, nivel_fallback: nv };
      if (!fin(o.delta_temporada_media)) { o.delta_temporada_media = o.delta_media; o.delta_temporada_sd = o.delta_sd; }
      return o;
    }
    return base;
  }
  function factores(pr, G, N, c, rng, n) {
    const d = new Array(n);
    for (let s = 0; s < n; s++) d[s] = c > 0 ? c * (pr.delta_temporada_media + num(pr.delta_temporada_sd, 0) * rng.n()) : 0;
    const Dd = fin(pr.D_forma_media) ? pr.D_forma_media * c : 0, kf = pr.kappa_forma_media;
    const phi = Array.from({ length: G }, (_, g) => (fin(kf) && kf > 0 ? Math.exp(-g / kf) : 0)), wbar = phi.reduce((a, b) => a + b, 0) / G;
    const forma = phi.map((p) => (1 + Dd * p) / (1 + Dd * wbar)), wN = forma.slice(0, N).reduce((a, b) => a + b, 0) / Math.min(N, G);
    return { temporada: d.map((x) => 1 + x), primeros: d.map((x) => (1 + x) * wN), forma, d };
  }

  // ------------------------------------------------------------------ 3. plantilla y minutos
  function miembro(rec, pres, lminClub, ligaD, base, esFichaje) {
    const P = D.meta.plantilla, LB = ligaBase(base, ligaD), U = D.meta.produccion;
    if (!rec) return { rec: null, presencia: pres, L: num(LB && LB.ref.banquillo, -0.5), L_sd: P.sd_sin_dato, sin_dato: 1, nuevo: 1, lmin_club: 0, lmin_fuera: 0, edad: NaN, pos3: null, eu: null };
    const L = fin(rec.L) ? rec.L : num(LB && LB.ref.banquillo, -0.5);
    const lm = logit(fin(rec.min_pct) ? rec.min_pct : D.meta.plantilla.min_previo_defecto || 0.25);
    const club = lminClub != null && !esFichaje;
    return { rec, presencia: pres, L, L_sd: fin(rec.L_sd) ? rec.L_sd : P.sd_sin_dato, sin_dato: fin(rec.L) ? 0 : 1, nuevo: club ? 0 : 1,
      lmin_club: club ? lminClub : 0, lmin_fuera: club ? 0 : lm, edad: rec.edad, pos3: rec.pos3, eu: rec.eu, nombre: rec.nombre, persona: rec.persona };
  }
  function encajes(P, ligaD, base, teamEu) {
    const LB = ligaBase(base, ligaD), tipico = (LB && LB.ref.pos) || { E: 0.45, A: 0.2, I: 0.35 }, B = D.meta.bases[base];
    const w = P.map((p) => Math.exp(Math.max(-6, Math.min(6, num(p.lmin_club, 0) + num(p.lmin_fuera, 0)))) * (1 + 0.5 * Math.tanh(num(p.L, 0))));
    const tot = w.reduce((a, b) => a + b, 0);
    P.forEach((p, i) => { if (!["E", "A", "I"].includes(p.pos3)) { p.encaje_pos = 0; return; } const sin = tot - w[i]; const cuota = sin > 0 ? (P.reduce((a, q, j) => a + (q.pos3 === p.pos3 ? w[j] : 0), 0) - w[i]) / sin : 0; p.encaje_pos = num(tipico[p.pos3], 0.3) - cuota; });
    const obj = (B.estilo_objetivo[teamEu] || B.estilo_objetivo._todos || new Array(6).fill(1 / 6));
    const ok = P.map((p) => Array.isArray(p.eu) && p.eu.every(fin));
    const W = w.map((x, i) => (ok[i] ? x : 0)), S = obj.map((_, k) => P.reduce((a, p, i) => a + (ok[i] ? p.eu[k] * W[i] : 0), 0)), sw = W.reduce((a, b) => a + b, 0);
    P.forEach((p, i) => { if (!ok[i]) { p.encaje_estilo = 0; return; } const s2 = sw - W[i]; const comp = s2 > 0 ? S.map((x, k) => (x - p.eu[k] * W[i]) / s2) : obj; p.encaje_estilo = p.eu.reduce((a, x, k) => a + x * (obj[k] - comp[k]), 0); });
    P.forEach((p) => { const e = fin(p.edad) ? (p.edad - 27) / 5 : 0; p.edad_c = e; p.edad_c2 = e * e; });
  }
  function utilidad(p) { const w = D.meta.utilidad; return D.meta.utilidad_rasgos.reduce((a, k) => a + num(w[k], 0) * num(p[k], 0), 0); }
  // asignar_minutos (bbfit.reemplazo): orden Plackett-Luce, mínimos por posición en el quinteto, rotación y curva del entrenador
  function asignar(P, U, pres, total, gm, rot, rotSd, curva0, nSim, rng) {
    const n = P.length, A = D.meta.asignacion, tope = A.max_min_partido * gm / 40 * total / (5 * gm), minimos = A.min_por_pos3;
    let curva = curva0.slice(); if (curva.length < n) curva = curva.concat(new Array(n - curva.length).fill(curva.length ? curva[curva.length - 1] : 0.1));
    curva = curva.slice(0, n).map((x) => Math.max(x, 1e-6));
    const M = [], T5 = [];
    for (let s = 0; s < nSim; s++) {
      const us = (U ? U[s] : P.map((p) => p.u)).slice(), g = P.map(() => rng.g());
      if (pres) { const fuera = pres.map((p) => rng.u() > p); if (fuera.filter((x) => !x).length < 5) { const o = pres.map((p, i) => [p, i]).sort((a, b) => b[0] - a[0]).slice(0, 5); o.forEach(([, i]) => (fuera[i] = false)); } fuera.forEach((f, i) => { if (f) us[i] = -Infinity; }); }
      let orden = us.map((x, i) => [x + g[i], i]).sort((a, b) => b[0] - a[0]).map((x) => x[1]).filter((i) => isFinite(us[i]));
      for (const grupo of Object.keys(minimos)) {
        const k = minimos[grupo];
        for (let it = 0; it < 20 && orden.slice(0, 5).filter((i) => P[i].pos3 === grupo).length < k; it++) {
          const fuera = orden.slice(5).filter((i) => P[i].pos3 === grupo); if (!fuera.length) break;
          const cuenta = {}; orden.slice(0, 5).forEach((i) => { cuenta[P[i].pos3] = (cuenta[P[i].pos3] || 0) + 1; });
          const sobran = orden.slice(0, 5).reverse().filter((i) => P[i].pos3 !== grupo && (cuenta[P[i].pos3] || 0) > num(minimos[P[i].pos3], 0)); if (!sobran.length) break;
          const a = orden.indexOf(sobran[0]), b = orden.indexOf(fuera[0]); [orden[a], orden[b]] = [orden[b], orden[a]];
        }
      }
      const R = Math.max(5, Math.min(orden.length, Math.round(rot + rotSd * rng.n())));
      const sc = curva.slice(0, R).reduce((a, b) => a + b, 0); let mins = curva.slice(0, R).map((x) => (x / sc) * total);
      for (let it = 0; it < 20; it++) { const ex = mins.reduce((a, m) => a + Math.max(m - tope, 0), 0); if (ex < 1e-9) break; mins = mins.map((m) => Math.min(m, tope)); const lib = mins.map((m) => m < tope - 1e-9); const sl = mins.reduce((a, m, i) => a + (lib[i] ? m : 0), 0); if (!lib.some(Boolean)) break; mins = mins.map((m, i) => (lib[i] ? m + ex * m / sl : m)); }
      const fila = new Array(n).fill(0), t5 = new Array(n).fill(false);
      orden.slice(0, R).forEach((i, r) => (fila[i] = mins[r])); orden.slice(0, 5).forEach((i) => (t5[i] = true));
      M.push(fila); T5.push(t5);
    }
    return { M, T5 };
  }
  function clasificar(mp, gs, gtg) {
    const u = D.meta.roles_umbral, sol = D.meta.roles_solape.gs;
    let r = mp < u.prof ? "RESIDUAL" : mp < u.rot ? "PROFUNDIDAD" : mp < u.tit ? "ROTACION" : mp < u.tit_seguro ? (gs >= sol ? "TITULAR" : "ROTACION") : "TITULAR";
    if (gtg && mp >= u.tit) r = "GO_TO_GUY";
    return r;
  }
  function tendencia(club) {
    const t = club.tendencia || [9, 1, []], c = D.meta.calibracion || {};
    return [num(t[0], 9) + num(c.rotacion_extra, 1), num(c.rotacion_sd_factor, 1) * num(t[1], 1), (t[2] || []).map((x) => num(x, 0))];
  }

  // ------------------------------------------------------------------ simulación principal
  /* op = { rec (registro del fichaje), club (fila de clubes.json), bajas: Set(persona), extras: [registros] (otros fichajes
   *        que entran como compañeros), nSim, semilla, sinAdaptacion } */
  function simular(op) {
    const meta = D.meta, rec = op.rec, club = op.club, base = club.base, ligaD = club.liga, gm = minPartido(ligaD), total = 5 * gm;
    const nSim = op.nSim || meta.n_sim, semilla = op.semilla ?? meta.semilla;
    const rng = rngDe((crc(`${rec.persona}|${ligaD}|${club.team}`) ^ semilla) >>> 0);
    const mets = meta.produccion.metricas, LB = ligaBase(base, ligaD), niveles = meta.intervalos;
    if (!LB) return { error: `sin constantes para ${ligaD}` };
    // 1. nivel latente traducido
    const z1 = Array.from({ length: nSim }, () => rng.n()), z2 = Array.from({ length: nSim }, () => rng.n());
    const tr = traducir(rec, ligaD, base, mets.concat(["rapm"]), z1, z2, rng, nSim), tr0 = traducir(rec, ligaD, base, mets.concat(["rapm"]));
    const L0 = fin(rec.L) ? rec.L : num(LB.ref.banquillo, -0.5), Lsd = fin(rec.L_sd) ? rec.L_sd : 0.4, Ls = z1.map((z) => L0 + Lsd * z);
    // 2. adaptación
    const lo = rec.liga, grupo = grupoNac(rec.nac, lo, ligaD), pos3 = ["E", "A", "I"].includes(rec.pos3) ? rec.pos3 : "A";
    const G = num(meta.adaptacion.partidos[ligaD], meta.adaptacion.partidos.defecto), N = meta.adaptacion.primeros;
    const contr = op.sinAdaptacion ? 0 : meta.adaptacion.contraccion;
    const AM = { pts_p100: "pts_p100", ts_pct: "ts_pct", usg_pct: "usg_pct", ast_pct: "ast_pct", oreb_p100: "reb_p100", dreb_p100: "reb_p100" };
    const priors = {}, fact = {};
    ["pts_p100", "ts_pct", "usg_pct", "ast_pct", "reb_p100", "L", "L_rel"].forEach((m) => { priors[m] = prior(lo, ligaD, grupo, pos3, m); fact[m] = factores(priors[m], G, N, contr, rng, nSim); });
    const Leff = Ls.map((x, s) => x + (fact.L.temporada[s] - 1));
    // 3. plantilla con el fichaje
    const bajas = op.bajas || new Set();
    let P = [];
    (club.plantilla || []).forEach(([rid, pres, lmc, persona]) => { if (persona === rec.persona || bajas.has(persona)) return; P.push(miembro(D.jug.get(rid) || null, num(pres, 1), lmc, ligaD, base, false)); P[P.length - 1].persona = persona; });
    (op.extras || []).forEach((r) => { if (r.persona !== rec.persona && !P.some((p) => p.persona === r.persona)) P.push(miembro(r, 1, null, ligaD, base, true)); });
    for (let k = P.length; k < meta.plantilla.minimo_jugadores - 1; k++) { P.push(miembro(null, 1, null, ligaD, base, false)); P[P.length - 1].persona = "__reemplazo_" + k; }
    P.push(miembro(rec, 1, null, ligaD, base, true)); P[P.length - 1].persona = rec.persona;
    const B = meta.bases[base], clubEu = club.eu;
    encajes(P, ligaD, base, clubEu);
    // recorte a la plantilla máxima (los de menos presencia y minutos previos fuera; el fichaje siempre entra)
    if (P.length > meta.plantilla.max_jugadores) { const iF = P.length - 1; const o = P.map((p, i) => [i === iF ? Infinity : num(p.presencia, 0) * 10 + num(p.lmin_club, 0) + num(p.lmin_fuera, 0), i]).sort((a, b) => b[0] - a[0]).slice(0, meta.plantilla.max_jugadores).map((x) => x[1]).sort((a, b) => a - b); P = o.map((i) => P[i]); }
    const iF = P.length - 1, cal = meta.calibracion || {}, ku = num(cal.escala_utilidad, 1);
    P.forEach((p) => (p.u = ku * utilidad(p)));
    const U = Array.from({ length: nSim }, (_, s) => { const r = P.map((p) => p.u); r[iF] += ku * num(meta.utilidad.L, 0) * (Leff[s] - L0); return r; });
    const [rot, rotSd, curva] = tendencia(club), pres = P.map((p, i) => (i === iF ? 1 : num(p.presencia, 1)));
    const { M, T5 } = asignar(P, U, pres, total, gm, rot, rotSd, curva, nSim, rng);
    const P0 = P.slice(0, iF), n0 = Math.max(200, Math.floor(nSim / 2));
    const M0 = P0.length >= 5 ? asignar(P0, null, pres.slice(0, iF), total, gm, rot, rotSd, curva, n0, rng).M : null;
    const resid = num(LB.min_residual, 0.06) * gm;
    const mF = M.map((f) => (f[iF] > 0 ? f[iF] : resid * (0.5 + rng.u())));
    // 4. uso
    const refD = LB.ref.uso || [20, 5];
    const usgNat = P.map((p, i) => { if (i === iF) return tr0.usg_pct; if (!p.rec) return NaN; return traducir(p.rec, ligaD, base, ["usg_pct"]).usg_pct; }).map((x) => Math.min(45, Math.max(5, fin(x) ? x : refD[0] - 0.5 * refD[1])));
    const usg0 = P.map((p, i) => (p.rec && fin(p.rec.usg) ? p.rec.usg : usgNat[i]));
    const gti0 = P.map((p) => (p.rec && fin(p.rec.gti) ? p.rec.gti : NaN));
    const refO = P.map((p) => (p.rec && ligaBase(base, p.rec.liga) ? ligaBase(base, p.rec.liga).ref.uso : refD));
    const usgF = tr.usg_pct.map((v, s) => (fin(v) ? v * fact.usg_pct.temporada[s] : usgNat[iF]));
    const pr = meta.produccion, gc = meta.go_to_guy;
    const beta = meta.beta_uso[pos3] || meta.beta_uso.todos || [-0.08, 0.1], bc = meta.companeros_ts || [0, 0];
    const USG2f = new Array(nSim), usgB = new Array(nSim), esGtg = new Array(nSim), Lbar = new Array(nSim), fUso = new Array(nSim);
    for (let s = 0; s < nSim; s++) {
      const fila = M[s], usg = usgNat.slice(); usg[iF] = usgF[s];
      let obj = 0, act = 0; fila.forEach((m, i) => { obj += pr.usg_medio_pista * m; act += m * usg[i]; });
      let f = act > 0 ? obj / act : 1; f = 1 + pr.amortiguar_uso * (f - 1); fUso[s] = f;
      const usg2 = usg.map((x) => x * f); USG2f[s] = usg2[iF]; usgB[s] = usg[iF];
      const gti = usg2.map((x, i) => (fin(gti0[i]) ? gti0[i] + gc.peso_uso * ((x - refD[0]) / refD[1] - (usg0[i] - refO[i][0]) / refO[i][1]) : -Infinity));
      const elig = fila.map((m) => m / gm >= 0.25);
      const orden = gti.map((x, i) => [elig[i] ? x : -Infinity, i]).sort((a, b) => b[0] - a[0]).map((x) => x[1]);
      const rango = orden.indexOf(iF);
      esGtg[s] = rango < gc.top_equipo && gti[iF] >= gc.umbral_gti && fila[iF] / gm >= gc.min_minutos_pct;
      let wl = 0, ww = 0; fila.forEach((m, i) => { if (i !== iF) { wl += m * P[i].L; ww += m; } }); Lbar[s] = wl / Math.max(ww, 1e-9);
    }
    // 5. compañeros
    const ctxO = fin(rec.ctx) ? rec.ctx : NaN, dL = Lbar.map((x) => (fin(ctxO) ? x - ctxO : 0));
    const bS = Array.from({ length: nSim }, () => bc[0] + bc[1] * rng.n()), betaS = Array.from({ length: nSim }, () => beta[0] + beta[1] * rng.n());
    // producción
    const prod = {};
    mets.forEach((m) => { const v = tr[m] || new Array(nSim).fill(NaN); prod[m] = AM[m] ? v.map((x, s) => x * fact[AM[m]].temporada[s]) : v.slice(); });
    const tsB = prod.ts_pct.slice();
    prod.ts_pct = tsB.map((t, s) => Math.min(pr.ts_max, Math.max(pr.ts_min, t + betaS[s] * (USG2f[s] - usgB[s]) + bS[s] * dL[s])));
    prod.usg_pct = USG2f.slice();
    prod.pts_p100 = prod.pts_p100.map((v, s) => v * (USG2f[s] / usgB[s]) * (prod.ts_pct[s] / tsB[s]));
    const ritmo = fin(club.ritmo) ? club.ritmo : num(LB.ref.ritmo, 72), disp = num(cal.disponibilidad, 0.85);
    const poss = mF.map((m) => (m / gm) * ritmo * G * disp), sig = fin(rec.sigma) ? rec.sigma : num(LB.ref.sigma, 12);
    const obs = {};
    mets.forEach((m) => {
      if (m === "pts_p100" && fin(sig)) { obs[m] = prod[m].map((v, s) => Math.max(0, v + sig * Math.sqrt(30 / Math.max(poss[s], 5)) * rng.n())); return; }
      const tiro = ["tsa", "fga", "fg2a", "fg3a"].includes(meta.exposicion[m]);
      obs[m] = ruido(m, ligaD, base, prod[m], poss.map((p, s) => p * (tiro ? USG2f[s] / 100 : 1)), rng);
    });
    // roles
    const rolS = mF.map((m, s) => clasificar(m / gm, T5[s][iF] ? 1 : 0, esGtg[s]));
    const pRol = Object.fromEntries(ROLES.map((r) => [r, rolS.filter((x) => x === r).length / nSim]));
    const rolEsp = ROLES.reduce((a, r) => (pRol[r] > pRol[a] ? r : a), ROLES[0]);
    const indiceRol = ROLES.reduce((a, r, i) => a + i * pRol[r], 0);
    const res = {
      persona: rec.persona, nombre: rec.nombre, liga_origen: lo, liga_destino: ligaD, team_destino: club.team, club_destino: club.nombre,
      temporada_destino: club.temporada, temporada_base: base, escenario: club.escenario, grupo_nacionalidad: grupo, pos3, n_sim: nSim,
      roles: pRol, rol_esperado: rolEsp, indice_rol: indiceRol, minutos: resumen(mF, niveles), min_pct: resumen(mF.map((m) => m / gm), niveles),
      p_titular: T5.filter((t) => t[iF]).length / nSim,
      produccion_p100: Object.fromEntries(mets.map((m) => [m, resumen(obs[m], niveles)])),
      traduccion_media: Object.fromEntries(mets.map((m) => [m, fin(tr0[m]) ? tr0[m] : null])),
      L: L0, L_sd: Lsd, L_efectivo: media(Leff), ritmo_destino: ritmo,
      uso: { natural: usgNat[iF], factor_equipo: media(fUso), d_usg: media(USG2f.map((x, s) => x - usgB[s])) },
      companeros: { L_bar: media(Lbar), L_origen: fin(ctxO) ? ctxO : null, efecto_ts: media(bS.map((b, s) => b * dL[s])) },
    };
    // por partido
    const possPg = mF.map((m) => (m / gm) * ritmo);
    res.por_partido = { posesiones: resumen(possPg, niveles) };
    Object.entries(pr.por_partido).forEach(([k, m]) => { const ms = Array.isArray(m) ? m : [m]; if (!ms.every((x) => obs[x])) return; res.por_partido[k] = resumen(possPg.map((p, s) => ms.reduce((a, x) => a + obs[x][s], 0) * p / 100), niveles); });
    // adaptación
    const fl = fact.L_rel, pa = priors.L_rel;
    res.adaptacion = { prior: pa, prior_pts: priors.pts_p100, contraccion: contr, adapt_pct_temporada: resumen(fl.temporada.map((x) => 100 * x), niveles),
      adapt_pct_primeros: resumen(fl.primeros.map((x) => 100 * x), niveles), adapt_pct_pts: resumen(fact.pts_p100.temporada.map((x) => 100 * x), niveles),
      delta_L: media(fact.L.temporada.map((x) => x - 1)), primeros_partidos: N, partidos_temporada: G,
      curva: fl.forma.slice(0, Math.min(G, 40)).map((f, g) => { const v = fl.temporada.map((t) => t * f); return [g, media(v), cuantil(v, 0.05), cuantil(v, 0.95)]; }),
      partidos_50: fin(pa.partidos_50) ? pa.partidos_50 : null, partidos_90: fin(pa.partidos_90) ? pa.partidos_90 : null };
    // estilo, complementariedad y entropías
    const ids = meta.estilos.map((e) => e.id), wm = P.map((_, i) => media(M.map((f) => f[i])));
    const okE = P.map((p) => Array.isArray(p.eu) && p.eu.every(fin));
    const comp = (filas, pesos) => { const s = ids.map(() => 0); let w = 0; filas.forEach((p, i) => { if (Array.isArray(p.eu) && p.eu.every(fin)) { p.eu.forEach((x, k) => (s[k] += x * pesos[i])); w += pesos[i]; } }); return w > 0 ? s.map((x) => x / w) : null; };
    const compCon = comp(P, wm), wm0 = M0 ? P0.map((_, i) => media(M0.map((f) => f[i]))) : null, compSin = (M0 && comp(P0, wm0)) || compCon;
    const pf = okE[iF] ? P[iF].eu : null, tp = Array.isArray(club.eu_probs) && club.eu_probs.every(fin) ? club.eu_probs : compSin;
    const obj = B.estilo_objetivo[clubEu] || B.estilo_objetivo._todos || ids.map(() => 1 / ids.length);
    const hueco = obj.map((o, k) => o - (compSin ? compSin[k] : o));
    const ast = P.map((p) => (p.rec && fin(p.rec.ast) ? p.rec.ast : NaN)), astMed = cuantil(ast, 0.5) ?? 10, astF = ast.map((a) => (fin(a) ? a : astMed));
    const hCon = entropiaNorm(wm.map((w, i) => w * usgNat[i])), hSin = M0 ? entropiaNorm(wm0.map((w, i) => w * usgNat[i])) : hCon;
    const hpCon = entropiaNorm(wm.map((w, i) => w * astF[i])), hpSin = M0 ? entropiaNorm(wm0.map((w, i) => w * astF[i])) : hpCon;
    res.estilo = { jugador: pf, equipo: tp, composicion_sin: compSin, composicion_con: compCon, objetivo: obj, distancia_js: pf ? js(pf, tp) : null,
      complementariedad: pf ? pf.reduce((a, x, k) => a + x * hueco[k], 0) : null,
      hueco_cubierto: pf ? ids[pf.map((x, k) => x * hueco[k]).reduce((b, x, k, a) => (x > a[b] ? k : b), 0)] : null,
      d_entropia_uso: hCon - hSin, d_entropia_pases: hpCon - hpSin, entropia_uso: [hSin, hCon], entropia_pases: [hpSin, hpCon], estilo_equipo: clubEu, ids };
    // impacto en el equipo y quintetos
    const rap = P.map((p, i) => { if (i === iF) return fin(tr0.rapm) ? tr0.rapm : 0; if (!p.rec) return 0; const v = traducir(p.rec, ligaD, base, ["rapm"]).rapm; return fin(v) ? v : 0; });
    const netCon = M.map((f) => (5 * f.reduce((a, m, i) => a + m * rap[i], 0)) / total);
    const netSin = M0 ? media(M0.map((f) => (5 * f.reduce((a, m, i) => a + m * rap[i], 0)) / total)) : NaN;
    const cnt = new Map(); M.forEach((f) => { const q = f.map((m, i) => [m, i]).sort((a, b) => b[0] - a[0]).slice(0, 5).map((x) => x[1]).sort((a, b) => a - b).join(","); cnt.set(q, (cnt.get(q) || 0) + 1); });
    const tops = [...cnt.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3).map(([k, n]) => { const q = k.split(",").map(Number); return { jugadores: q.map((i) => P[i].persona), nombres: q.map((i) => P[i].nombre || "s/d"), prob: n / nSim, con_fichaje: q.includes(iF), net: q.reduce((a, i) => a + rap[i], 0) }; });
    res.equipo = { net_con: media(netCon), net_sin: netSin, d_net: media(netCon) - netSin, d_net_lo90: cuantil(netCon, 0.05) - netSin, d_net_hi90: cuantil(netCon, 0.95) - netSin, rapm_fichaje: rap[iF], quintetos: tops };
    // componentes del Fit, índice y avisos
    let lt = 0, wt = 0; P.forEach((p, i) => { if (i !== iF) { lt += wm[i] * p.L; wt += wm[i]; } });
    const sigRef = LB.ref.sigma, hr = rec.hrol;
    const x = { nivel: res.L_efectivo - lt / Math.max(wt, 1e-9), rol: indiceRol, estilo: -(fin(res.estilo.distancia_js) ? res.estilo.distancia_js : 0.25),
      complementariedad: num(res.estilo.complementariedad, 0), entropia: res.estilo.d_entropia_uso + res.estilo.d_entropia_pases,
      adaptacion: num(res.adaptacion.adapt_pct_temporada.media, 100) - 100,
      volatilidad: -(fin(rec.sigma) && fin(sigRef) ? rec.sigma / sigRef - 1 : 0), incertidumbre: -Lsd, h_rol: -(fin(hr) ? hr : 1.2) };
    res.componentes_crudos = x;
    res.fit = indiceFit(x);
    res.avisos = avisos(res, rec, base, ligaD);
    res.plantilla = P.map((p, i) => ({ persona: p.persona, nombre: p.nombre || null, pos3: p.pos3 || null, L: p.L, minutos: wm[i], minutos_sin: M0 && i < iF ? wm0[i] : null, fichaje: i === iF, extra: !!(p.rec && op.extras && op.extras.includes(p.rec)) })).sort((a, b) => b.minutos - a.minutos);
    return res;
  }
  function indiceFit(x) {
    const F = D.meta.fit, C = D.meta.componentes;
    if (!F) return { total: null, componentes: Object.fromEntries(Object.keys(C).map((k) => [k, null])) };
    const contrib = {}; Object.keys(x).forEach((f) => { if (!(f in F.w)) return; const v = fin(x[f]) ? x[f] : F.media[f]; contrib[f] = F.w[f] * (v - F.media[f]) / (F.sd[f] || 1); });
    const comp = Object.fromEntries(Object.entries(C).map(([k, fs]) => [k, fs.reduce((a, f) => a + num(contrib[f], 0), 0)]));
    return { total: F.b0 + Object.values(comp).reduce((a, b) => a + b, 0), base: F.b0, componentes: comp, rasgos: contrib };
  }
  function avisos(res, rec, base, ligaD) {
    const a = D.meta.avisos, out = [], B = D.meta.bases[base];
    if (num(rec.min_total, 0) < a.muestra_pequena_min || num(rec.gp, 0) < a.muestra_pequena_partidos) out.push({ tipo: "muestra_pequena", texto: `Muestra pequeña en origen (${Math.round(num(rec.min_total, 0))}' en ${Math.round(num(rec.gp, 0))} partidos).` });
    const dO = (B.ligas[rec.liga] || {}).nivel, dD = (B.ligas[ligaD] || {}).nivel;
    if (fin(dO) && fin(dD) && Math.abs(dD - dO) > a.distancia_liga_alta) out.push({ tipo: "liga_lejana", texto: `Salto de nivel grande entre ligas (${(dD - dO > 0 ? "+" : "")}${(dD - dO).toFixed(2)} DT).` });
    const sdp = rec.sd ? rec.sd[0] : NaN;
    if ((fin(sdp) && sdp > a.incertidumbre_alta_sd) || res.L_sd > a.incertidumbre_alta_sd) out.push({ tipo: "incertidumbre_alta", texto: "Incertidumbre alta en su nivel traducido." });
    const ro = rec.rol, ir = ROLES.indexOf(ro);
    if (ir >= 0 && Math.abs(res.indice_rol - ir) >= a.cambio_rol) out.push({ tipo: "cambio_rol", texto: `Rol muy distinto al de origen (${ro} → ${res.rol_esperado}).` });
    const p80 = (B.ligas[ligaD] || { ref: {} }).ref.sigma_p80;
    if (fin(rec.sigma) && fin(p80) && rec.sigma > p80) out.push({ tipo: "volatilidad_alta", texto: "Rendimiento muy variable partido a partido (σ alta)." });
    const pr = res.adaptacion.prior; if (["sin_datos", "error", "global"].includes(pr.nivel_fallback) || num(pr.n, 0) < 8) out.push({ tipo: "adaptacion_generica", texto: "Adaptación estimada con poca información propia de ese cambio de liga." });
    return out;
  }
  // Minutos endógenos de una plantilla completa (sin fichaje): «Simular equipo completo»
  function minutosEquipo(recs, club, nSim) {
    const base = club.base, ligaD = club.liga, gm = minPartido(ligaD), total = 5 * gm, rng = rngDe(crc(`${club.liga}|${club.team}|equipo`));
    const lmc = new Map((club.plantilla || []).map((x) => [x[3], x[2]]));
    const P = recs.map((r) => { const m = miembro(r, 1, lmc.has(r.persona) ? lmc.get(r.persona) : null, ligaD, base, !lmc.has(r.persona)); m.persona = r.persona; return m; });
    if (P.length < 5) return null;
    encajes(P, ligaD, base, club.eu);
    const ku = num((D.meta.calibracion || {}).escala_utilidad, 1); P.forEach((p) => (p.u = ku * utilidad(p)));
    const [rot, rotSd, curva] = tendencia(club), n = nSim || D.meta.n_sim;
    const { M, T5 } = asignar(P, null, P.map(() => 1), total, gm, rot, rotSd, curva, n, rng);
    return P.map((p, i) => ({ persona: p.persona, minutos: media(M.map((f) => f[i])), mediana: cuantil(M.map((f) => f[i]), 0.5), lo50: cuantil(M.map((f) => f[i]), 0.25), hi50: cuantil(M.map((f) => f[i]), 0.75), p_titular: T5.filter((t) => t[i]).length / n }));
  }
  const api = { cargar, simular, minutosEquipo, prior, grupoNac, traducir, clasificar, ROLES, get datos() { return D; } };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else raiz.SIM2 = api;
})(typeof window !== "undefined" ? window : globalThis);
