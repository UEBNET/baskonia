// Prueba en navegador de la normalización v5.1 (encargo v5.1 F6): selector, tablas regular_v51.json y vara_v51.json.
// Requiere una carpeta servida con la forma del Artifact (artifact/kerno/* + datos/normalizados/ con regular.json,
// regular_v51.json, indice.json, vara.json y vara_v51.json; ver docs/v5_1/07_F6_integracion.md) y Playwright:
//   node tests/js/v51_normalizacion.js http://localhost:8790
// La conversión de vara de la v5 se contrasta con la referencia Python bbnorm5.salidas.producto51.convertir.
const { chromium } = require("playwright");
const base = process.argv[2] || "http://localhost:8790";
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1400, height: 1000 } });
  const errores = [], fallidas = [];
  p.on("pageerror", (e) => errores.push(e.message));
  p.on("requestfailed", (r) => fallidas.push(r.url()));
  const r404 = []; p.on("response", (r) => { if (r.status() >= 400 && !r.url().endsWith(".gz.txt")) r404.push(r.status() + " " + r.url().replace(base, "")); });
  await p.goto(`${base}/index.html`); await p.waitForTimeout(8000);
  const est = await p.evaluate(async () => {
    const T = await temporada("2025-26");
    const r = T.rows.find((x) => g(x, "liga") === "acb" && g(x, "fuente_norm") === "V5.1" && (g(x, "min") || 0) > 800);
    const o = { norm: T.norm, normv: NORMV, v51: !!VARA51, filas: T.rows.length, nombre: g(r, "nombre"), liga: g(r, "liga"),
      fg3: [g(r, "fg3_pct"), g(r, "fg3_pct_lo"), g(r, "fg3_pct_hi")], comb: g(r, "v51_comb"), solo: g(r, "v51_solo"), pos: g(r, "pos3") };
    CTX.liga = "feb1";                           // vara Primera FEB
    o.c32 = convVara32(r, "fg3_pct"); o.c = convVara(r, "fg3_pct"); o.c5 = conv51(r, "fg3_pct", VARA51.metricas.fg3_pct);
    o.w = VARA51.metricas.fg3_pct.w;
    o.pts = [convVara32(r, "pts_p100"), convVara(r, "pts_p100")];
    o.ts = [convVara32(r, "ts_pct"), convVara(r, "ts_pct")];     // derivada: sólo v3.2
    CTX.liga = "euroleague";
    o.pie = document.body.innerText.includes("normalización v5.1");
    return o;
  });
  console.log(JSON.stringify(est, null, 0));
  await p.click("#setBtn"); await p.waitForTimeout(300);
  const seg = await p.evaluate(() => [...document.querySelectorAll("#setNorm button")].map((x) => x.innerText + ":" + x.getAttribute("aria-pressed")));
  console.log("selector", seg);
  await Promise.all([p.waitForNavigation({ timeout: 30000 }).catch(() => null), p.click('#setNorm button[data-v="v32"]')]);
  await p.waitForTimeout(8000);
  const e32 = await p.evaluate(async () => { const T = await temporada("2025-26"); return { norm: T.norm, normv: NORMV, v42: !!T.v42, pie: document.body.innerText.includes("normalización v3.2") }; });
  console.log("tras cambiar a v3.2", JSON.stringify(e32));
  await p.evaluate(() => localStorage.setItem("kerno.norm", "v51"));
  // vista clásica: Datos normalizados con la vara de la ACB
  await p.goto(`${base}/clasico.html`); await p.waitForTimeout(6000);
  const cl = await p.evaluate(async () => { st.src = "norm"; const d = await loadPhase("2025-26", "regular", "euroleague"); const a = await loadPhase("2025-26", "regular", "acb");
    const i = d.idx, k = d.rows.findIndex((r) => r[i.fuente_norm] === "V5.1" && r[i.liga] === "feb1");
    return { norm: NORMV, n: d.rows.length, v51_cols: i.v51_comb != null, fila: d.rows[k][i.nombre], el: d.rows[k][i.fg3_pct], acb: a.rows[k][i.fg3_pct], pct: a.rows[k][i.fg3_pct_pctel] }; }).catch((e) => ({ error: String(e) }));
  console.log("clasico", JSON.stringify(cl));
  console.log("errores", errores.slice(0, 5)); console.log("404", [...new Set(r404)].slice(0, 15));
  await b.close();
})();
