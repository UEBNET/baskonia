/* Cerno Analytics · Modelo de equipo v4.0 en el navegador · 05-11-2026
 * Capa 4 (Net̂ de una plantilla y Δ̂Net de un fichaje) y anclas NIVEL CERNO (NC) e IMPACTO (IM) a partir de las muestras
 * Monte Carlo del motor del Atlas (simulador.js: res._mc, out._mc) y de las tablas exportadas por bbequipo/exportar_atlas.py
 * (v40/jugadores_v40.json, v40/referencias_v40.json). Mismas β (F1), parejas (F2-A, rango 4), red aditiva (F3), calibración
 * c·T + intervalos (F4) y referencias F_ref / F_mov con sus capas de calibración (F5) que la v4.0 en Python; lo único que
 * cambia son los minutos, que aquí salen del motor v3.3 del navegador (aproximación declarada en los informes).
 *   NC = 100·E[F_ref(C)], C = (min/partido ÷ min del partido) × pts/100, F_ref = liga de destino × puesto; calibrado (cal_nc).
 *   IM = 100·E[F_mov(Δ̂Net)], Δ̂Net = c_grupo · (T con − T sin), T = Σ p_i β_i + Σ P_ij φ_ij + Σ p_i h_i; calibrado al on/off (cal_im).
 */
(function (raiz) {
  "use strict";
  const fin = (x) => typeof x === "number" && isFinite(x);
  const V = { J: null, R: null, P: null, cache: new Map() };
  function cargar(loader) {
    if (!V.P) V.P = Promise.all([loader("v40/jugadores_v40.json"), loader("v40/referencias_v40.json")]).then(([j, r]) => { V.J = j; V.R = r; return V; });
    return V.P;
  }
  const listo = () => !!(V.J && V.R);
  function crc(s) { let h = 2166136261 >>> 0; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619) >>> 0; } return h; }
  function rngDe(semilla) {
    let a = semilla >>> 0, sobra = null;
    const u = () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
    const n = () => { if (sobra !== null) { const s = sobra; sobra = null; return s; } let x, y, r; do { x = 2 * u() - 1; y = 2 * u() - 1; r = x * x + y * y; } while (r >= 1 || r === 0); const f = Math.sqrt(-2 * Math.log(r) / r); sobra = y * f; return x * f; };
    return { u, n };
  }
  const media = (a) => { const v = a.filter(fin); return v.length ? v.reduce((s, x) => s + x, 0) / v.length : NaN; };
  const desv = (a) => { const v = a.filter(fin); if (v.length < 2) return 0; const m = media(v); return Math.sqrt(v.reduce((s, x) => s + (x - m) ** 2, 0) / (v.length - 1)); };
  function cuantil(arr, p) { const v = arr.filter(fin).sort((x, y) => x - y); if (!v.length) return NaN; const h = (v.length - 1) * p, i = Math.floor(h); return i + 1 < v.length ? v[i] + (h - i) * (v[i + 1] - v[i]) : v[i]; }

  // ------------------------------------------------------------------ distribuciones de referencia y calibraciones
  function empirica(exp) {
    if (!exp || !exp.cuantiles) return null;
    const nodos = Object.entries(exp.cuantiles).map(([k, x]) => [Number(k), x]).filter((o) => fin(o[0]) && fin(o[1])).sort((a, b) => a[0] - b[0]);
    if (nodos.length < 2) return null;
    const ps = nodos.map((o) => o[0]), xs = nodos.map((o) => o[1]);
    const F = (x) => { if (!fin(x)) return NaN; if (x <= xs[0]) return 0; if (x >= xs[xs.length - 1]) return 1;
      let i = 1; while (i < xs.length && xs[i] < x) i++; const x0 = xs[i - 1], x1 = xs[i]; return x1 > x0 ? ps[i - 1] + (ps[i] - ps[i - 1]) * (x - x0) / (x1 - x0) : ps[i]; };
    F.n = exp.n || 0; F.xs = xs; F.ps = ps; return F;
  }
  function calib(cal, v) {      // g(v crudo) por interpolación lineal en la rejilla exportada (0..100)
    if (!cal || !fin(v)) return NaN; const x = cal.x, y = cal.y;
    if (v <= x[0]) return y[0]; if (v >= x[x.length - 1]) return y[y.length - 1];
    let i = 1; while (i < x.length && x[i] < v) i++; return y[i - 1] + (y[i] - y[i - 1]) * (v - x[i - 1]) / (x[i] - x[i - 1]);
  }
  function rangoCal(cal, vCrudo, centro) {   // cuantiles 10 y 90 del realizado condicionados al decil del crudo (como anclas.calibrar_nc)
    if (!cal || !fin(vCrudo)) return [NaN, NaN];
    const b = cal.bordes; let k = 0; for (let i = 1; i < b.length - 1; i++) if (b[i] != null && vCrudo >= b[i]) k = i;
    k = Math.min(k, cal.q10.length - 1);
    return [Math.min(cal.q10[k], centro), Math.max(cal.q90[k], centro)];
  }
  const grupoF4 = (liga) => (V.R.grupo_f4 || {})[liga] || "otras";
  const grupoIM = (liga) => (V.R.grupo_im || {})[liga] || "resto";
  function cal4(liga) { const g = grupoF4(liga), c = V.R.calibracion_f4, k = (c.por_grupo || {})[g] || c.conjunto; return { grupo: g, c: k.prediccion.c, d: k.prediccion.d, s0: k.intervalo.s0, q: k.intervalo.q, n: k.prediccion.n }; }

  // ------------------------------------------------------------------ insumos por jugador (reglas de equipo.Insumos)
  function ultimo(obj, t) { if (!obj) return null; let best = null; for (const k in obj) if (k <= t && (best == null || k > best)) best = k; return best; }
  function valor(pid, liga, t) {
    const p = V.J.personas[pid];
    if (p && p.b) { const k = ultimo(p.b, t); if (k != null && fin(p.b[k][0])) return { beta: p.b[k][0], sd: fin(p.b[k][1]) ? p.b[k][1] : V.J.tau, fuente: "beta", temporada: k }; }
    if (p && p.g && fin(p.g[t])) return { beta: p.g[t], sd: V.J.tau, fuente: "prior", temporada: t };
    const nn = V.J.nivel_nuevo || {};
    return { beta: fin(nn[liga]) ? nn[liga] : V.J.nivel_nuevo_global, sd: V.J.tau * 1.5, fuente: "nuevo", temporada: null };
  }
  function rasgos(pid, t, tRec) {   // [h, a_1..a_r]: perfil de la temporada del registro si existe; si no, el último ≤ t; si no, sin perfil
    const p = V.J.personas[pid], r = V.J.rango || 4, cero = [V.J.h0 || 0].concat(new Array(r).fill(0));
    if (!p || !p.z) return cero;
    if (tRec && p.z[tRec]) return p.z[tRec];
    const k = ultimo(p.z, t); return k != null ? p.z[k] : cero;
  }
  // T por simulación de una plantilla: Pm (nSim × n) cuotas p_i = minutos_i / minutos del partido (Σ p_i = 5)
  function valorEquipo(personas, Pm, liga, t, temporadas, rng, muestrearBeta = true) {
    const n = personas.length, w = V.J.w || [];
    const val = personas.map((p) => valor(p, liga, t)), b = val.map((v) => v.beta), sd = val.map((v) => v.sd);
    const Z = personas.map((p, i) => rasgos(p, t, temporadas ? temporadas[i] : null)), h = Z.map((z) => z[0]);
    const Phi = Array.from({ length: n }, () => new Array(n).fill(0));
    for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) { let s = 0; for (let k = 0; k < w.length; k++) s += w[k] * (Z[i][k + 1] || 0) * (Z[j][k + 1] || 0); Phi[i][j] = Phi[j][i] = s; }
    const T = new Array(Pm.length), Tadd = new Array(Pm.length), Tphi = new Array(Pm.length), Th = new Array(Pm.length);
    for (let s = 0; s < Pm.length; s++) {
      const p = Pm[s]; let ta = 0, th = 0, S = 0, S2 = 0;
      for (let i = 0; i < n; i++) { const B = b[i] + (muestrearBeta && rng ? sd[i] * rng.n() : 0); ta += p[i] * B; th += p[i] * h[i]; S += p[i]; S2 += p[i] * p[i]; }
      let tp = 0; for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) tp += p[i] * p[j] * Phi[i][j];
      const pp = (S * S - S2) / 2; tp = tp * 10 / Math.max(pp, 1e-9);
      Tadd[s] = ta; Tphi[s] = tp; Th[s] = th; T[s] = ta + tp + th;
    }
    return { T, T_aditivo: Tadd, T_phi: Tphi, T_h: Th, beta: b, sd, fuente: val.map((v) => v.fuente), h };
  }

  // ------------------------------------------------------------------ anclas
  function percentilEsperado(F, muestras) { const pct = muestras.map((x) => 100 * F(x)).filter(fin); return { media: media(pct), lo: cuantil(pct, 0.10), hi: cuantil(pct, 0.90) }; }
  function impactoDe(delta, sTot, liga, rng, n = 300) {
    const g = grupoIM(liga), F = empirica((V.R.F_mov || {})[g]);
    if (!F || !fin(delta)) return { IM: NaN, grupo_im: g };
    const m = Array.from({ length: n }, () => delta + sTot * rng.n()), e = percentilEsperado(F, m);
    const IM = calib(V.R.cal_im, e.media), [lo, hi] = rangoCal(V.R.cal_im, e.media, IM);
    return { IM, IM_lo80: lo, IM_hi80: hi, IM_crudo: e.media, IM_crudo_lo80: e.lo, IM_crudo_hi80: e.hi, grupo_im: g, n_mov: F.n, pct_delta: 100 * F(delta) };
  }
  function nivelDe(Cs, liga, pos3) {
    const pos = ["E", "A", "I"].includes(pos3) ? pos3 : "A";
    const F = empirica((V.R.F_ref || {})[`${liga}|${pos}`]) || empirica((V.R.F_ref || {})[`${liga}|todas`]);
    if (!F || !Cs.length) return { NC: NaN, motivo: "sin población de referencia" };
    const e = percentilEsperado(F, Cs), NC = calib(V.R.cal_nc, e.media), [lo, hi] = rangoCal(V.R.cal_nc, e.media, NC);
    return { NC, NC_lo80: lo, NC_hi80: hi, NC_crudo: e.media, NC_crudo_lo80: e.lo, NC_crudo_hi80: e.hi, pct_mediana: 100 * F(cuantil(Cs, 0.5)), n_ref: F.n, pos,
      C: { mediana: cuantil(Cs, 0.5), lo80: cuantil(Cs, 0.10), hi80: cuantil(Cs, 0.90), media: media(Cs) } };
  }
  /* Fichaje: anclas y Δ̂Net a partir de res = SIM.simular({...}) (con res._mc), el registro del fichaje y el club de destino. */
  function anclasFichaje(res, rec, club) {
    if (!listo() || !res || res.error || !res._mc) return null;
    const mc = res._mc, liga = club.liga, t = club.temporada || "9999", gm = mc.gm, k4 = cal4(liga);
    const rng = rngDe((crc(`${rec.persona}|${liga}|${club.team}|v40`)) >>> 0);
    const Pcon = mc.M.map((f) => f.map((m) => m / gm));
    const con = valorEquipo(mc.personas, Pcon, liga, t, mc.temporadas, rng);
    let dT = null, sin = null;
    if (mc.M0 && mc.M0.length) {
      const Psin = mc.M0.map((f) => f.map((m) => m / gm));
      sin = valorEquipo(mc.personas.slice(0, mc.iF), Psin, liga, t, mc.temporadas.slice(0, mc.iF), rng);
      dT = con.T.map((x, s) => x - sin.T[s % sin.T.length]);
    }
    const out = { liga, temporada: t, grupo_f4: k4.grupo, c: k4.c, s0: k4.s0, q: k4.q, T_con: media(con.T), T_sin: sin ? media(sin.T) : null,
      beta: con.beta[mc.iF], beta_sd: con.sd[mc.iF], fuente_beta: con.fuente[mc.iF], h: con.h[mc.iF], n_sim: mc.M.length };
    if (dT) {
      const delta = k4.c * media(dT), sdMc = k4.c * desv(dT), sTot = Math.sqrt(sdMc * sdMc + k4.s0 * k4.s0);
      Object.assign(out, { delta_net: delta, delta_lo80: delta - k4.q * sTot, delta_hi80: delta + k4.q * sTot, sd_mc: sdMc, s_total: sTot,
        aditivo: k4.c * media(con.T_aditivo.map((x, s) => x - sin.T_aditivo[s % sin.T_aditivo.length])) }, impactoDe(delta, sTot, liga, rng));
    }
    // NC: C por simulación (minutos del fichaje × pts/100 observados), reescalado a las cifras publicadas del motor (v3.3)
    const pts = mc.pts || [], mF = mc.mF || [];
    if (pts.length && mF.length) {
      const fm = res.minutos && fin(res.minutos.mediana) && cuantil(mF, 0.5) > 0 ? res.minutos.mediana / cuantil(mF, 0.5) : 1;
      const pp = res.produccion_p100 && res.produccion_p100.pts_p100, fp = pp && fin(pp.mediana) && cuantil(pts, 0.5) > 0 ? pp.mediana / cuantil(pts, 0.5) : 1;
      const Cs = mF.map((m, s) => Math.max(0, (m * fm / gm) * (fin(pts[s]) ? pts[s] * fp : NaN))).filter(fin);
      Object.assign(out, nivelDe(Cs, liga, rec.pos3), { f_min: fm, f_pts: fp });
    }
    return out;
  }
  /* Liga: T de todas las plantillas de (liga, temporada) con el motor (minutosEquipo) → media de la liga y ranking. */
  function ligaT(SIM, SIMD, liga, temporada, nSim = 300) {
    const key = `${liga}|${temporada}|${nSim}`; if (V.cache.has(key)) return V.cache.get(key);
    const eqs = [];
    (SIMD.clubes || []).filter((c) => c.liga === liga && c.temporada === temporada).forEach((club) => {
      const recs = (club.plantilla || []).map((x) => SIMD.jug.get(x[0])).filter(Boolean);
      if (recs.length < 7) return;
      let out = null; try { out = SIM.minutosEquipo(recs, club, nSim); } catch (e) { out = null; }
      if (!out || !out._mc) return;
      const mc = out._mc, Pm = mc.M.map((f) => f.map((m) => m / mc.gm));
      const v = valorEquipo(mc.personas, Pm, liga, temporada, mc.temporadas, null, false);
      eqs.push({ team: club.team, nombre: club.nombre, T: media(v.T), T_sd: desv(v.T), n_plantilla: recs.length, n_sin_beta: v.fuente.filter((f) => f === "nuevo").length });
    });
    const lg = { liga, temporada, equipos: eqs, media: eqs.length ? media(eqs.map((e) => e.T)) : NaN, n: eqs.length };
    V.cache.set(key, lg); return lg;
  }
  /* Net proyectado de una plantilla frente a su liga (puntos por 100 posesiones sobre la media de la liga), con rango del 80 %. */
  function netEquipo(out, club, lg, personasExtra) {
    if (!listo() || !out || !out._mc || !lg || !fin(lg.media)) return null;
    const mc = out._mc, liga = club.liga, t = club.temporada || "9999", k4 = cal4(liga);
    const Pm = mc.M.map((f) => f.map((m) => m / mc.gm)), v = valorEquipo(mc.personas, Pm, liga, t, mc.temporadas, null, false);
    const T = media(v.T), Tsd = desv(v.T), rel = k4.c * (T - lg.media), semi = k4.q * Math.sqrt((k4.c * Tsd) ** 2 + k4.s0 ** 2);
    const otros = lg.equipos.filter((e) => e.team !== club.team), puesto = 1 + otros.filter((e) => e.T > T).length;
    return { T, T_sd: Tsd, T_aditivo: media(v.T_aditivo), T_phi: media(v.T_phi), T_h: media(v.T_h), net: rel, lo80: rel - semi, hi80: rel + semi, puesto, n: otros.length + 1,
      c: k4.c, s0: k4.s0, q: k4.q, grupo_f4: k4.grupo, media_liga: lg.media, n_sin_beta: v.fuente.filter((f) => f === "nuevo").length, fuentes: v.fuente, betas: v.beta, personas: mc.personas };
  }
  function ligaNet(lg, liga) {
    const k4 = cal4(liga || lg.liga);
    return lg.equipos.map((e) => { const rel = k4.c * (e.T - lg.media), semi = k4.q * Math.sqrt((k4.c * e.T_sd) ** 2 + k4.s0 ** 2); return { ...e, net: rel, lo80: rel - semi, hi80: rel + semi }; }).sort((a, b) => b.net - a.net);
  }
  /* Plantilla: NC de cada jugador (su producción en su liga × sus minutos proyectados) e IM = qué pierde el equipo sin él. */
  function anclasPlantilla(SIM, out, club, recs, roles, nSimSin = 240) {
    if (!listo() || !out || !out._mc) return [];
    const mc = out._mc, liga = club.liga, t = club.temporada || "9999", gm = mc.gm, k4 = cal4(liga);
    const Pm = mc.M.map((f) => f.map((m) => m / gm)), all = valorEquipo(mc.personas, Pm, liga, t, mc.temporadas, null, false), Tall = media(all.T);
    return mc.personas.map((per, i) => {
      const rec = mc.recs[i], rng = rngDe(crc(`${per}|${liga}|${club.team}|plantilla`) >>> 0), r = { persona: per, minutos: media(mc.M.map((f) => f[i])), beta: all.beta[i], fuente_beta: all.fuente[i] };
      let pts = NaN; try { pts = rec ? SIM.traducir(rec, liga, club.base, ["pts_p100"]).pts_p100 : NaN; } catch (e) { pts = NaN; }
      if (fin(pts)) Object.assign(r, nivelDe(mc.M.map((f) => Math.max(0, f[i] / gm * pts)), liga, rec && rec.pos3), { pts_p100: pts });
      const sinRecs = recs.filter((x) => x && x.persona !== per);
      if (sinRecs.length >= 5) {
        let o2 = null; try { o2 = SIM.minutosEquipo(sinRecs, club, nSimSin, roles); } catch (e) { o2 = null; }
        if (o2 && o2._mc) { const m2 = o2._mc, v2 = valorEquipo(m2.personas, m2.M.map((f) => f.map((m) => m / m2.gm)), liga, t, m2.temporadas, null, false);
          const dT = all.T.map((x, s) => x - v2.T[s % v2.T.length]), delta = k4.c * media(dT), sdMc = k4.c * desv(dT), sTot = Math.sqrt(sdMc * sdMc + k4.s0 * k4.s0);
          Object.assign(r, { delta_net: delta, delta_lo80: delta - k4.q * sTot, delta_hi80: delta + k4.q * sTot, sd_mc: sdMc }, impactoDe(delta, sTot, liga, rng)); }
      }
      return r;
    });
  }
  const api = { cargar, listo, anclasFichaje, ligaT, netEquipo, ligaNet, anclasPlantilla, valor, valorEquipo, empirica, calib, rangoCal, cal4, grupoIM, grupoF4, VERSION: "v4.0", get datos() { return V; } };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else raiz.CernoV40 = api;
})(typeof window !== "undefined" ? window : globalThis);
