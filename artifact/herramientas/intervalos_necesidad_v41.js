// V41_F4 §8.4 · anchura del rango del «ajuste» de «Por necesidad»: actual (extremos sumados) frente a errores independientes.
// node intervalos_necesidad_v41.js  (página servida en http://localhost:8766/ con datos/normalizados/2026-27)
const { chromium } = require("playwright");
(async () => {
  const br = await chromium.launch(); const pg = await br.newPage();
  await pg.goto("http://localhost:8766/index.html#necesidad", { waitUntil: "load", timeout: 120000 });
  await pg.waitForTimeout(8000);
  const r = await pg.evaluate(async () => {
    CTX.temp = "2026-27"; const T = await temporada(CTX.temp); await referencia(); try { await v4(); } catch (e) {}
    const out = { temp: CTX.temp, liga: CTX.liga, perfiles: {} };
    for (const [k, P] of Object.entries(PERFILES)) {
      const filas = [];
      for (const r of T.rows) {
        if ((g(r, "min") || 0) < (CTX.temp === "2026-27" ? 100 : 400)) continue;
        const es = P.w.map(([m, w, d]) => [est(r, m, d), w]); if (es.some(([e]) => !e)) continue;
        const sw = es.reduce((a, [, w]) => a + w, 0), p = es.reduce((a, [e, w]) => a + w * e.p, 0) / sw;
        const cl = es.reduce((a, [e, w]) => a + w * e.pl, 0) / sw, ch = es.reduce((a, [e, w]) => a + w * e.ph, 0) / sw;
        const il = p - Math.sqrt(es.reduce((a, [e, w]) => a + (w * (e.p - e.pl)) ** 2, 0)) / sw, ih = p + Math.sqrt(es.reduce((a, [e, w]) => a + (w * (e.ph - e.p)) ** 2, 0)) / sw;
        filas.push({ n: g(r, "nombre"), liga: g(r, "liga"), p, cl, ch, il, ih });
      }
      filas.sort((a, b) => b.p - a.p);
      const med = (a) => a.slice().sort((x, y) => x - y)[Math.floor(a.length / 2)];
      out.perfiles[k] = { n: filas.length, ancho_actual_mediana: med(filas.map((f) => f.ch - f.cl)), ancho_indep_mediana: med(filas.map((f) => f.ih - f.il)),
        top40_actual: med(filas.slice(0, 40).map((f) => f.ch - f.cl)), top40_indep: med(filas.slice(0, 40).map((f) => f.ih - f.il)),
        morgan: filas.filter((f) => /Juwan Morgan/.test(f.n)).map((f) => ({ ...f, p: Math.round(f.p), cl: Math.round(f.cl), ch: Math.round(f.ch), il: Math.round(f.il), ih: Math.round(f.ih) })) };
    }
    return out;
  });
  console.log(JSON.stringify(r, null, 1)); await br.close();
})();
