// Prueba en navegador del Atlas con liga = 0 elegible (vara compartida con la Mesa) y de la «Zona que ocupa cada estilo».
// Requiere una carpeta servida con la forma del Artifact (index.html = artifact/mesa-multiliga.html, atlas/, datos/ con
// normalizados/vara.json; ver artifact/empaquetar.py) y Playwright con Chromium:
//   node tests/js/atlas_vara.js http://localhost:8765
const { chromium } = require("playwright");
const base = process.argv[2] || "http://localhost:8765";
const fallos = [];
const comprobar = (c, txt) => { if (!c) fallos.push(txt); console.log(`${c ? "ok   " : "FALLO"} ${txt}`); };
// textos visibles y atributos de ayuda (sin <script>) con una plantilla sin resolver
const plantillas = () => { const v = []; document.querySelectorAll("body *:not(script):not(style)").forEach((e) => {
  ["data-tip", "title", "aria-label"].forEach((a) => { const x = e.getAttribute(a); if (x) v.push(x); });
  e.childNodes.forEach((n) => { if (n.nodeType === 3) v.push(n.textContent); }); }); return v.filter((x) => /\$\{/.test(x)).length; };
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROMIUM || "/opt/pw-browsers/chromium" });
  const errores = [];
  // 1 · Atlas con la ACB como liga = 0
  const ctx = await b.newContext({ viewport: { width: 1400, height: 1000 } });
  await ctx.addInitScript(() => { try { localStorage.setItem("mm.vara", "acb"); } catch (e) { /* */ } });
  const p = await ctx.newPage(); p.on("pageerror", (e) => errores.push(e.message));
  await p.goto(`${base}/atlas/index.html#comparar`); await p.waitForSelector("#cargando", { state: "hidden", timeout: 120000 }); await p.waitForTimeout(2500);
  const e = await p.evaluate(() => { const L = ESC.fam("nivel").ligas["2025-26"];
    return { vara: ESC.vara, sACB: ESC.S("nivel", L.acb, "2025-26"), sEL: ESC.S("nivel", L.euroleague, "2025-26"), varaj: !!VARAJ,
      nota: document.querySelector(".nivNota").textContent }; });
  comprobar(e.vara === "acb" && Math.abs(e.sACB) < 1e-9 && e.sEL > 0, `nivel: ACB = 0 y Euroliga ${e.sEL.toFixed(1)} en la escala ±100`);
  comprobar(/Liga Endesa/.test(e.nota) && e.varaj, "textos de la escala y vara.json con la liga elegida");
  let lit = 0;
  for (const t of ["comparar", "simulador", "equipo", "parecidos", "quimica", "informe"]) { await p.evaluate((t) => irA(t), t); await p.waitForTimeout(t === "comparar" || t === "quimica" ? 2500 : 7000); lit += await p.evaluate(plantillas); }
  comprobar(lit === 0, "ninguna plantilla sin resolver en las seis pestañas");
  const eq = await p.evaluate(() => document.querySelector("#p-equipo").innerText);
  comprobar(/Ranking frente a la Liga Endesa/.test(eq) && /club medio de la Liga Endesa/.test(eq), "equipo completo: ranking y nivel frente a la Liga Endesa");
  await ctx.close();
  // 2 · zona de cada estilo (elipsoides dentro del rango de los datos)
  const q = await b.newPage({ viewport: { width: 1400, height: 1000 } }); q.on("pageerror", (x) => errores.push(x.message));
  await q.goto(`${base}/atlas/index.html#comparar`); await q.waitForSelector("#cargando", { state: "hidden", timeout: 120000 }); await q.waitForTimeout(2000);
  await q.evaluate(() => { const c = document.getElementById("cElip"); if (!c.checked) { c.checked = true; c.dispatchEvent(new Event("change")); } }); await q.waitForTimeout(3000);
  const z = await q.evaluate(() => { const d = document.getElementById("mapa"), ms = d.data.filter((t) => t.type === "mesh3d");
    const ext = (k) => Math.max(...ms.map((t) => Math.max(...t[k].map(Math.abs))));
    const cl = d.data.filter((t) => t.type === "scatter3d").flatMap((t) => t.x || []).filter(isFinite).map(Math.abs);
    return { n: ms.length, ext: Math.max(ext("x"), ext("y"), ext("z")), datos: Math.max(...cl) }; });
  comprobar(z.n > 0 && z.ext <= Math.max(1.5, 1.5 * z.datos), `zona de cada estilo: ${z.n} elipsoides dentro del mapa (|máx| ${z.ext.toFixed(2)} frente a ${z.datos.toFixed(2)} de los datos)`);
  // 3 · el selector de Ajustes de la Mesa llega al Atlas
  const m = await b.newPage({ viewport: { width: 1400, height: 1000 } }); m.on("pageerror", (x) => errores.push(x.message));
  await m.goto(`${base}/index.html`); await m.waitForTimeout(3000);
  await m.evaluate(() => ebIr("estilos", "comparar")); await m.waitForTimeout(12000);
  await m.click("#cxSetBtn"); await m.selectOption("#ebVara", "lnb"); await m.waitForTimeout(4000);
  const fr = m.frames().find((f) => /atlas\/index.html/.test(f.url()) && !/vista=claves/.test(f.url()));
  const v = await fr.evaluate(() => ESC.vara), sel = await m.evaluate(() => document.getElementById("varaSel").value);
  comprobar(v === "lnb" && sel === "lnb", "Ajustes · Liga = 0 cambia el Atlas y los selectores de la Mesa");
  comprobar(!errores.length, "sin errores de página" + (errores.length ? ": " + errores.slice(0, 3).join(" | ") : ""));
  await b.close();
  console.log(fallos.length ? `${fallos.length} comprobaciones fallidas` : "todas las comprobaciones pasan");
  process.exit(fallos.length ? 1 : 0);
})();
