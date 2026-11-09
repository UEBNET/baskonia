/* Kerno Analytics · capa v4.1 «ecosistema del club» en el Atlas · F4 (09-11-2026)
 * Tablas de producto: v41/producto.json (python -m bbequipo.ecosistema producto): Landing por grupo de traspaso, confianza
 * de cada salida (alta · moderada · baja, decisión del CEO del 09-11-2026) y glosario i18n ES/EN.
 * Escenario (altas con el rol que fija el analista, bajas, combinados) con el motor de minutos del Atlas (simulador.js,
 * minutosEquipo) y la capa 4 de la v4.0 (v40.js): mismas fórmulas que bbequipo/ecosistema/escenarios.py —
 *   ΔNet = c·(T̄ escenario − T̄ base), rango 80 % = ± q·√((c·DT_mc)² + s0²)          (capa 4, calibración por grupo)
 *   Coste de su ausencia(j) = c·(T̄ base − T̄ base sin j), mismo rango                   (V41_F3: confianza moderada)
 *   Δ minutos y Δ uso de cada compañero, simulación a simulación (números aleatorios comunes del motor), rango 80 %;
 *     si el rango incluye 0: «sin cambio apreciable» (V41_F3: confianza baja)
 *   uso con suma fija: U'_i = U_i·f, f = 20·Σ M / Σ M·U (redistribuir_uso con amortiguar = 1)
 *   atribución de Shapley exacta por movimiento (hasta 4 movimientos)
 *   NIVEL KERNO de cada jugador con los minutos del escenario: 100·E[F_ref(C)], C = min/partido ÷ min del partido × pts/100,
 *     calibrado (cal_nc), como CernoV40 (aproximación del navegador: los minutos son los del motor JS, declarada en v40.js).
 */
(function (raiz) {
  "use strict";
  const fin = (x) => typeof x === "number" && isFinite(x);
  const V = { P: null, prod: null, cache: new Map() };
  const media = (a) => { let s = 0, n = 0; for (const x of a) if (fin(x)) { s += x; n++; } return n ? s / n : NaN; };
  const desv = (a) => { const m = media(a); let s = 0, n = 0; for (const x of a) if (fin(x)) { s += (x - m) ** 2; n++; } return n > 1 ? Math.sqrt(s / (n - 1)) : 0; };
  function cuantil(arr, p) { const v = arr.filter(fin).sort((x, y) => x - y); if (!v.length) return NaN; const h = (v.length - 1) * p, i = Math.floor(h); return i + 1 < v.length ? v[i] + (h - i) * (v[i + 1] - v[i]) : v[i]; }

  function cargar(loader) { if (!V.P) V.P = loader("v41/producto.json").then((p) => { V.prod = p; return p; }).catch((e) => { console.error("v4.1:", e); return null; }); return V.P; }
  const listo = () => !!V.prod;
  const lang = () => ((document.documentElement.lang || "es").slice(0, 2) === "en" ? "en" : "es");
  const t = (k) => (V.prod && V.prod.i18n[lang()][k]) || k;
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const num = (x, d = 1) => (fin(x) ? (lang() === "es" ? x.toFixed(d).replace(".", ",") : x.toFixed(d)) : "–");
  const sg = (x, d = 1) => (fin(x) ? (x > 0 ? "+" : x < 0 ? "−" : "") + num(Math.abs(x), d) : "–");
  const FL = '<i class="k-arrow" aria-hidden="true"></i>';

  // ------------------------------------------------------------------ confianza (medidor de tres segmentos + etiqueta)
  function confianza(clave) {
    const s = V.prod && V.prod.sellos[clave]; if (!s) return "";
    const n = s.segmentos, et = lang() === "es" ? `confianza ${s.confianza_es}` : `${s.confianza_en} confidence`;
    const tip = `${s.salida} · ${et}${s.estado === "propuesto" ? (lang() === "es" ? " (propuesta, pendiente de confirmar)" : " (proposed, pending sign-off)") : ""} · ${s.fuente}`;
    return `<span class="k-conf" data-n="${n}" data-tip="${esc(tip)}"><i class="${n >= 1 ? "on" : ""}"></i><i class="${n >= 2 ? "on" : ""}"></i><i class="${n >= 3 ? "on" : ""}"></i><span>${esc(et)}</span></span>`;
  }
  // rango que incluye 0 → «sin cambio apreciable» (decisión del CEO §1.7)
  const cambio = (m, lo, hi, d = 1, u = "") => (fin(lo) && fin(hi) && lo <= 0 && hi >= 0 ? `<span class="muted">${esc(t("sin_cambio"))}</span>` : `<b>${sg(m, d)}</b>${u} <span class="muted">[${sg(lo, d)} a ${sg(hi, d)}]</span>`);

  // ------------------------------------------------------------------ Landing (grupo de traspaso)
  function landing(grupo) {
    const g = V.prod && V.prod.landing.grupos[grupo]; if (!g || !g.mostrar) return null;
    const n = lang() === "es" ? g.es : g.en;
    return { ...g, texto: n[1] ? `${esc(n[0])} ${FL} ${esc(n[1])}` : esc(n[0]) };
  }
  function landingHtml(grupo) {
    const g = landing(grupo);
    if (!g) return `<p class="v2nota">${lang() === "es" ? "Landing: sin cambio apreciable para su grupo de traspaso (el rango del 80 % incluye 0)." : "Landing: no measurable change for his transfer group (the 80% range includes 0)."}</p>`;
    return `<p style="margin:2px 0"><b>${esc(t("landing"))}</b> · ${g.texto}: <b>${sg(g.pct, 1)} %</b> <span class="muted">[${sg(g.lo80, 1)} a ${sg(g.hi80, 1)}]</span></p>${confianza("landing")}
      <p class="v2nota">${esc(t("landing_def"))} (${g.n} ${lang() === "es" ? "traspasos" : "transfers"}). ${lang() === "es" ? "Es una cifra del grupo, no del jugador." : "It is a group figure, not an individual one."}</p>`;
  }

  // ------------------------------------------------------------------ escenario
  function nivelDe(Cs, liga, pos3) {
    const R = raiz.CernoV40 && raiz.CernoV40.datos.R; if (!R) return null;
    const pos = ["E", "A", "I"].includes(pos3) ? pos3 : "A";
    const F = raiz.CernoV40.empirica((R.F_ref || {})[`${liga}|${pos}`]) || raiz.CernoV40.empirica((R.F_ref || {})[`${liga}|todas`]);
    if (!F || !Cs.length) return null;
    const pct = Cs.map((x) => 100 * F(x)).filter(fin), m = media(pct), NC = raiz.CernoV40.calib(R.cal_nc, m), [lo, hi] = raiz.CernoV40.rangoCal(R.cal_nc, m, NC);
    return { NC, lo, hi };
  }
  function evaluar(ctx, idx) {
    const key = idx.join(","); if (ctx.cache.has(key)) return ctx.cache.get(key);
    const S = new Set(idx), fuera = new Set(), roles = new Map(), extra = [];
    ctx.movs.forEach((m, k) => { if (!S.has(k)) return; if (m.t === "baja") fuera.add(m.persona); else { extra.push(m.rec); if (m.rol) roles.set(m.rec.persona, m.rol); } });
    const recs = ctx.base.filter((r) => !fuera.has(r.persona)).concat(extra.filter((r) => !ctx.base.some((b) => b.persona === r.persona)));
    let out = null; try { out = ctx.SIM.minutosEquipo(recs, ctx.club, ctx.nSim, roles); } catch (e) { out = null; }
    if (!out || !out._mc) { ctx.cache.set(key, null); return null; }
    const mc = out._mc, gm = mc.gm, Pm = mc.M.map((f) => f.map((x) => x / gm));
    const v = raiz.CernoV40.valorEquipo(mc.personas, Pm, ctx.club.liga, ctx.club.temporada || "9999", mc.temporadas, null, false);
    const U = mc.recs.map((r) => ctx.uso(r)), f = mc.M.map((row) => { let a = 0, b = 0; row.forEach((x, i) => { a += x; b += x * U[i]; }); return b > 0 ? (20 * a) / b : 1; });
    const r = { T: v.T, gm, pid: new Map(mc.personas.map((p, i) => [p, i])), M: mc.M, U, f, recs: mc.recs };
    ctx.cache.set(key, r); return r;
  }
  const minDe = (e, p) => { const i = e && e.pid.get(p); return i == null ? e.M.map(() => 0) : e.M.map((f) => f[i]); };
  const usoDe = (e, p) => { const i = e && e.pid.get(p); return i == null ? e.M.map(() => NaN) : e.f.map((x) => e.U[i] * x); };
  function shapley(ctx, valor) {        // valor: de una evaluación a un número; exacto con hasta 4 movimientos
    const m = ctx.movs.length, phi = new Array(m).fill(0), fact = (n) => (n <= 1 ? 1 : n * fact(n - 1));
    for (let k = 0; k < m; k++) {
      const resto = [...Array(m).keys()].filter((i) => i !== k);
      for (let mask = 0; mask < 1 << resto.length; mask++) {
        const S = resto.filter((_, b) => mask & (1 << b)), w = (fact(S.length) * fact(m - S.length - 1)) / fact(m);
        const a = evaluar(ctx, [...S, k].sort((x, y) => x - y)), b = evaluar(ctx, S.slice().sort((x, y) => x - y));
        if (a && b) phi[k] += w * (valor(a) - valor(b));
      }
    }
    return phi;
  }
  function escenario(o) {
    // o = { SIM, SIMD, club, bajas: Set(persona), altas: [{rec, rol}], nSim }
    if (!raiz.CernoV40 || !raiz.CernoV40.listo() || !o.club) return null;
    const club = o.club, base = (club.plantilla || []).map((x) => o.SIMD.jug.get(x[0])).filter(Boolean);
    if (base.length < 7) return null;
    const movs = o.altas.filter((a) => a && a.rec).map((a) => ({ t: "alta", rec: a.rec, rol: a.rol, persona: a.rec.persona, nombre: a.rec.nombre }))
      .concat([...o.bajas].filter((p) => base.some((r) => r.persona === p)).map((p) => { const r = base.find((x) => x.persona === p); return { t: "baja", persona: p, nombre: r.nombre }; }));
    const key = JSON.stringify([club.liga, club.team, club.temporada, movs.map((m) => [m.t, m.persona, m.rol || ""]), o.nSim]);
    if (V.cache.has(key)) return V.cache.get(key);
    const usoC = new Map(), ctx = { SIM: o.SIM, club, base, movs, nSim: o.nSim || 300, cache: new Map(),
      uso: (r) => { if (!r) return 20; if (usoC.has(r.persona)) return usoC.get(r.persona); let u = NaN; try { u = o.SIM.traducir(r, club.liga, club.base, ["usg_pct"]).usg_pct; } catch (e) { u = NaN; } u = fin(u) ? Math.min(45, Math.max(5, u)) : 18; usoC.set(r.persona, u); return u; } };
    const todos = [...movs.keys()], e0 = evaluar(ctx, []), e1 = evaluar(ctx, todos);
    if (!e0 || !e1) return null;
    const k4 = raiz.CernoV40.cal4(club.liga), dT = e1.T.map((x, s) => x - e0.T[s % e0.T.length]);
    const semi = (d) => k4.q * Math.sqrt((k4.c * desv(d)) ** 2 + k4.s0 ** 2);
    const res = { club, movs, k4, delta_net: k4.c * media(dT), delta_semi: semi(dT), exacto: movs.length <= 4, bajas: [], companeros: [], altas: [] };
    // Coste de su ausencia de cada baja (en la plantilla de partida)
    movs.forEach((m, k) => { if (m.t !== "baja") return; const ej = evaluar(ctx, [k]); if (!ej) return;
      const d = e0.T.map((x, s) => x - ej.T[s % ej.T.length]), c = k4.c * media(d);
      res.bajas.push({ persona: m.persona, nombre: m.nombre, coste: c, lo: c - semi(d), hi: c + semi(d) }); });
    // atribución exacta (≤ 4 movimientos)
    const phiNet = res.exacto && movs.length ? shapley(ctx, (e) => k4.c * media(e.T)) : null;
    res.phi_net = phiNet;
    const sigue = base.filter((r) => !movs.some((m) => m.t === "baja" && m.persona === r.persona));
    const gm = e1.gm, nc = (e, r) => { if (!r) return null; let pts = NaN; try { pts = o.SIM.traducir(r, club.liga, club.base, ["pts_p100"]).pts_p100; } catch (x) { pts = NaN; }
      return fin(pts) ? nivelDe(minDe(e, r.persona).map((mm) => Math.max(0, (mm / gm) * pts)), club.liga, r.pos3) : null; };
    sigue.forEach((r) => {
      const m0 = minDe(e0, r.persona), m1 = minDe(e1, r.persona), dm = m1.map((x, s) => x - m0[s % m0.length]);
      const u0 = usoDe(e0, r.persona), u1 = usoDe(e1, r.persona), du = u1.map((x, s) => x - u0[s % u0.length]);
      let atrib = null;
      if (res.exacto && movs.length) { const phi = shapley(ctx, (e) => media(minDe(e, r.persona))); let kb = 0; phi.forEach((x, k) => { if (Math.abs(x) > Math.abs(phi[kb])) kb = k; }); atrib = { k: kb, phi: phi[kb], todos: phi }; }
      res.companeros.push({ persona: r.persona, nombre: r.nombre, min0: media(m0), min1: media(m1), min1_lo: cuantil(m1, 0.1), min1_hi: cuantil(m1, 0.9), dmin: media(dm), dmin_lo: cuantil(dm, 0.1), dmin_hi: cuantil(dm, 0.9),
        duso: media(du), duso_lo: cuantil(du, 0.1), duso_hi: cuantil(du, 0.9), nc0: nc(e0, r), nc1: nc(e1, r), atrib });
    });
    movs.forEach((m) => { if (m.t !== "alta") return; const ma = minDe(e1, m.persona); res.altas.push({ persona: m.persona, nombre: m.nombre, rol: m.rol, min1: media(ma), min1_lo: cuantil(ma, 0.1), min1_hi: cuantil(ma, 0.9), nc1: nc(e1, m.rec) }); });
    res.companeros.sort((a, b) => b.min1 - a.min1);
    V.cache.set(key, res); if (V.cache.size > 30) V.cache.delete(V.cache.keys().next().value);
    return res;
  }

  // ------------------------------------------------------------------ presentación
  function panelHtml(res, nombreMov) {
    if (!res) return "";
    const es = lang() === "es", ncTxt = (x) => (x && fin(x.NC) ? `<b>${Math.round(x.NC)}</b> <span class="muted">[${Math.round(x.lo)}–${Math.round(x.hi)}]</span>` : "–");
    const movNom = (k) => { const m = res.movs[k]; return m ? `${m.t === "alta" ? (es ? "llegada de " : "arrival of ") : (es ? "salida de " : "departure of ")}${esc(nombreMov(m))}` : ""; };
    const net = `<div class="v41net"><span class="label">${esc(t("net_escenario"))}</span><p style="margin:2px 0">Δ Net ${cambio(res.delta_net, res.delta_net - res.delta_semi, res.delta_net + res.delta_semi, 1, " pts/100")}</p>${confianza("net_equipo")}
      ${res.phi_net ? `<p class="v2nota">${es ? "Atribución (Shapley exacto):" : "Attribution (exact Shapley):"} ${res.phi_net.map((x, k) => `${movNom(k)} ${sg(x, 1)}`).join(" · ")}</p>` : res.movs.length > 4 ? `<p class="v2nota">${es ? "Con más de 4 movimientos no se muestra la atribución exacta." : "With more than 4 moves, exact attribution is not shown."}</p>` : ""}</div>`;
    const bajas = res.bajas.length ? `<div class="v41bajas"><span class="label">${esc(t("coste_ausencia"))}</span>${res.bajas.map((b) => `<p style="margin:2px 0">${esc(nombreMov(b))}: ${cambio(b.coste, b.lo, b.hi, 1, " pts/100")}</p>`).join("")}${confianza("coste_ausencia")}<p class="v2nota">${esc(t("coste_ausencia_def"))}.</p></div>` : "";
    const filas = res.companeros.map((c) => `<tr><td>${esc(nombreMov(c))}</td><td class="num">${num(c.min0, 1)} ${FL} <b>${num(c.min1, 1)}</b> <span class="muted">[${num(c.min1_lo, 0)}–${num(c.min1_hi, 0)}]</span></td><td>${cambio(c.dmin, c.dmin_lo, c.dmin_hi, 1, "'")}</td><td>${cambio(c.duso, c.duso_lo, c.duso_hi, 1, "")}</td><td>${ncTxt(c.nc0)} ${FL} ${ncTxt(c.nc1)}</td><td class="v2nota">${c.atrib && Math.abs(c.atrib.phi) >= 0.5 ? `${movNom(c.atrib.k)} (${sg(c.atrib.phi, 1)}')` : ""}</td></tr>`).join("");
    const altas = res.altas.map((a) => `<tr class="v41alta"><td>${esc(nombreMov(a))} <span class="muted">(${es ? "alta" : "signing"})</span></td><td class="num"><b>${num(a.min1, 1)}</b> <span class="muted">[${num(a.min1_lo, 0)}–${num(a.min1_hi, 0)}]</span></td><td></td><td></td><td>${ncTxt(a.nc1)}</td><td></td></tr>`).join("");
    const tabla = `<div class="v41comp"><span class="label">${esc(t("cambio_companeros"))}</span>
      <div class="v41scroll"><table class="v2t v41t"><thead><tr><th>${es ? "Jugador" : "Player"}</th><th>${es ? "Minutos (antes, después [80 %])" : "Minutes (before, after [80%])"}</th><th>${es ? "Δ minutos" : "Δ minutes"}</th><th>${es ? "Δ uso" : "Δ usage"}</th><th>${esc(t("nc_escenario"))}</th><th>${es ? "Sobre todo por" : "Mostly due to"}</th></tr></thead><tbody>${filas}${altas}</tbody></table></div>
      <div class="v41pie"><span>${es ? "Cambios" : "Changes"} ${confianza("delta_companeros")}</span><span>NIVEL KERNO ${confianza("nivel_kerno")}</span></div>
      <p class="v2nota">${esc(t("cambio_companeros_def"))}. ${esc(t("reparto_total"))}.</p></div>`;
    return `<div class="v41eco"><h4>${es ? "Ecosistema del club en este escenario" : "Club ecosystem in this scenario"} <small class="muted">· v4.1</small></h4>${net}${bajas}${tabla}
      <p class="v2nota">${es ? "Minutos del motor del Atlas con los movimientos del escenario (rol fijado sólo para las altas) frente a la plantilla de partida; rangos del 80 %. Capa 4 de la v4.0 para el Net." : "Minutes from the Atlas engine with the scenario's moves (role fixed only for signings) versus the starting roster; 80% ranges. v4.0 team layer for Net."}</p></div>`;
  }

  const CSS = `.k-conf{display:inline-flex;align-items:center;gap:3px;font:500 11px/1.2 var(--font-mono);letter-spacing:.08em;text-transform:uppercase;color:var(--text-2);margin:4px 0}
.k-conf i{display:inline-block;width:12px;height:6px;border:1px solid var(--brand)}.k-conf i.on{background:var(--brand)}.k-conf span{margin-left:6px}
.v41eco{border-top:1.2px solid var(--rule-strong);margin-top:24px;padding-top:12px}.v41eco h4{margin:0 0 8px}
.v41eco .v41net,.v41eco .v41bajas{margin-bottom:12px}.v41t td.num{font-family:var(--font-mono);white-space:nowrap}.v41t tr.v41alta td{border-top:1px solid var(--rule)}
.v41pie{display:flex;flex-wrap:wrap;gap:8px 24px;align-items:center;font-size:12px;color:var(--text-2);margin-top:6px}
#sEcoV41,.v41eco{min-width:0;max-width:100%}.v41scroll{overflow-x:auto;max-width:100%;-webkit-overflow-scrolling:touch}.v41t{min-width:640px}`;
  function estilos() { if (document.getElementById("k-v41-css")) return; const s = document.createElement("style"); s.id = "k-v41-css"; s.textContent = CSS; document.head.appendChild(s); }

  const api = { cargar, listo, t, confianza, landing, landingHtml, escenario, panelHtml, estilos, VERSION: "v4.1", get datos() { return V; } };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else raiz.KernoV41 = api;
})(typeof window !== "undefined" ? window : globalThis);
