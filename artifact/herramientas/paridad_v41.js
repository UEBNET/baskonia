// F4 v4.1 · paridad Python–JS de las cifras nuevas del ecosistema (KernoV41.escenario).
// Motor de minutos y capa 4 sintéticos y deterministas (mismos números en los dos lados): el JS calcula ΔNet, Coste de su
// ausencia, Δ minutos/uso, Shapley y NIVEL KERNO; tests/test_ecosistema_v41.py recalcula lo mismo con numpy y compara.
// node paridad_v41.js <salida.json>
const fs = require("fs");
const salida = process.argv[2];
globalThis.document = { documentElement: { lang: "es" } };
const K = require("../kerno/atlas/v41/ecosistema.js");
const N = 40, GM = 40;
function rngDe(s) { let a = s >>> 0; return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
const jug = new Map(), base = [];
for (let i = 0; i < 12; i++) { const p = "P" + i; jug.set(p, { persona: p, nombre: "J" + i, pos3: ["E", "A", "I"][i % 3], temporada: "2025-26", q: 1 + (i % 5), usg: 14 + i, pts: 12 + i }); base.push([p]); }
const altaRec = { persona: "A1", nombre: "Alta", pos3: "A", temporada: "2025-26", q: 4, usg: 24, pts: 21 };
// motor sintético: minutos ∝ q·(1 + 0,3·u_s), u_s común por simulación (números aleatorios comunes), Σ = 5·GM
const SIM = {
  minutosEquipo(recs, club, n, roles) {
    const r = rngDe(7), M = [];
    for (let s = 0; s < n; s++) { const u = recs.map(() => r()); const w = recs.map((x, i) => x.q * (1 + 0.3 * u[i]) * (roles && roles.get && roles.get(x.persona) === "TITULAR" ? 1.5 : 1));
      const W = w.reduce((a, b) => a + b, 0); M.push(w.map((x) => (5 * GM * x) / W)); }
    return { _mc: { gm: GM, personas: recs.map((x) => x.persona), temporadas: recs.map((x) => x.temporada), M, recs } };
  },
  traducir(r, liga, b, mets) { return mets[0] === "usg_pct" ? { usg_pct: r.usg } : { pts_p100: r.pts }; },
};
const beta = (p) => (p === "A1" ? 3 : (Number(p.slice(1)) - 5) * 0.8);
const cuant = Object.fromEntries([...Array(21).keys()].map((k) => [(k / 20).toFixed(2), 2 * k]));
globalThis.CernoV40 = {
  listo: () => true,
  cal4: () => ({ c: 0.43, q: 1.24, s0: 4.79, grupo: "x" }),
  valorEquipo: (personas, Pm) => ({ T: Pm.map((f) => f.reduce((a, x, i) => a + x * beta(personas[i]), 0)) }),
  empirica: (e) => { if (!e) return null; const xs = Object.values(e.cuantiles), ps = Object.keys(e.cuantiles).map(Number);
    return (x) => (x <= xs[0] ? 0 : x >= xs[xs.length - 1] ? 1 : (() => { let i = 1; while (xs[i] < x) i++; return ps[i - 1] + (ps[i] - ps[i - 1]) * (x - xs[i - 1]) / (xs[i] - xs[i - 1]); })()); },
  calib: (c, v) => v, rangoCal: (c, v, cen) => [cen - 20, cen + 20],
  datos: { R: { F_ref: { "acb|E": { n: 21, cuantiles: cuant }, "acb|A": { n: 21, cuantiles: cuant }, "acb|I": { n: 21, cuantiles: cuant } }, cal_nc: {} } },
};
K.datos.prod = { i18n: { es: {}, en: {} }, sellos: {}, landing: { grupos: {} } };
const SIMD = { jug };
const club = { liga: "acb", team: "1", temporada: "2025-26", base: "2025-26", plantilla: base };
const res = K.escenario({ SIM, SIMD, club, bajas: new Set(["P11"]), altas: [{ rec: altaRec, rol: "TITULAR" }], nSim: N });
fs.writeFileSync(salida, JSON.stringify({ N, GM, res: { delta_net: res.delta_net, delta_semi: res.delta_semi, phi_net: res.phi_net, bajas: res.bajas,
  companeros: res.companeros.map((c) => ({ persona: c.persona, dmin: c.dmin, dmin_lo: c.dmin_lo, dmin_hi: c.dmin_hi, duso: c.duso, nc0: c.nc0 && c.nc0.NC, nc1: c.nc1 && c.nc1.NC, phi: c.atrib && c.atrib.todos })) } }, null, 1));
console.log("ok", res.delta_net, res.bajas[0].coste);
