// Prueba en navegador del Atlas: referencia de la escala por contexto (la vara global de Ajustes sólo rige en «Jugadores»;
// Planificación = liga del club elegido; Estilos = la propia liga de cada equipo y jugador) y «Zona que ocupa cada estilo».
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
    return { vara: ESC.vara, sACB: ESC.S("nivel", L.acb, "2025-26"), sEL: ESC.S("nivel", L.euroleague, "2025-26"), varaj: !!VARAJ }; });
  comprobar(e.vara === "acb" && Math.abs(e.sACB) < 1e-9 && e.sEL > 0, `vara global (Jugadores): ACB = 0 y Euroliga ${e.sEL.toFixed(1)}`);
  let lit = 0;
  for (const t of ["comparar", "simulador", "equipo", "parecidos", "quimica", "informe"]) { await p.evaluate((t) => irA(t), t); await p.waitForTimeout(t === "comparar" || t === "quimica" ? 2500 : 7000); lit += await p.evaluate(plantillas); }
  comprobar(lit === 0, "ninguna plantilla sin resolver en las seis pestañas");
  const c = await p.evaluate(() => { irA("comparar"); return { nota: document.querySelector("#p-comparar .nivNota").textContent, ents: [...document.querySelectorAll("#ents .ent")].map((x) => x.innerText) }; });
  comprobar(/su propia liga/.test(c.nota) && c.ents.some((t) => /Liga Endesa = 0/.test(t)) && c.ents.some((t) => /Euroliga = 0/.test(t)), "Estilos: cada club frente a su propia liga (no la vara global)");
  const eq = await p.evaluate(() => { st.eq.liga = "euroleague"; irA("equipo"); return document.querySelector("#p-equipo").innerText; });
  comprobar(/Ranking frente a la Euroliga/.test(eq), "Simular equipo completo: referencia = liga del club (Euroliga), no la vara global (ACB)");
  const sim = await p.evaluate(async () => { await cargarSim(); const g = JG.filter((j) => /Gimeno/.test(j.nombre)).sort((a, b) => b.temporada.localeCompare(a.temporada))[0];
    const cl = CL.find((x) => x.liga === "feb3" && x.temporada === "2025-26" && /BASKONIA|Baskonia/.test(x.nombre_club)); st.sim.liga = "feb3"; st.sim.temp = "2025-26"; st.sim.club = cl.clave_club; st.sim.fich = [{ k: jKey(g), m: null }]; st.sim.bajas = []; st.sim.ejemplo = false;
    irA("simulador"); await new Promise((r) => setTimeout(r, 2500)); pintarSim();
    return { tip: [...document.querySelectorAll("#sV2 [data-tip]")].map((e) => e.getAttribute("data-tip")).find((t) => /Nivel:/.test(t)) || "", vara: ESC.vara }; });
  comprobar(/Tercera FEB = 0/.test(sim.tip) && sim.vara === "acb", "Simular fichajes: Pablo Gimeno a Baskonia (Tercera FEB) con Tercera FEB = 0; la vara global no cambia");
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
  comprobar(v === "lnb" && sel === "lnb", "Ajustes · Liga = 0 llega al Atlas (Jugadores) y a los selectores de la Mesa");
  comprobar(!errores.length, "sin errores de página" + (errores.length ? ": " + errores.slice(0, 3).join(" | ") : ""));
  await b.close();
  console.log(fallos.length ? `${fallos.length} comprobaciones fallidas` : "todas las comprobaciones pasan");
  process.exit(fallos.length ? 1 : 0);
})();
