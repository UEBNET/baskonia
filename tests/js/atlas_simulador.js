// Prueba en navegador del Atlas (simulador v2 y nomenclatura de estilos unificada).
// Requiere una carpeta servida con la forma del Artifact publicado (index.html, atlas/, atlas/estilos/, atlas/simulador/,
// atlas/simulador_v2.js; ver artifact/empaquetar.py) y Playwright con Chromium:
//   node tests/js/atlas_simulador.js http://localhost:8765 [carpeta_capturas]
const { chromium } = require("playwright");
const base = process.argv[2] || "http://localhost:8765", out = process.argv[3];
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROMIUM || "/opt/pw-browsers/chromium" });
  const errores = [], fallos = [];
  const comprobar = (c, txt) => { if (!c) fallos.push(txt); console.log(`${c ? "ok   " : "FALLO"} ${txt}`); };
  const p = await b.newPage({ viewport: { width: 1400, height: 1000 } });
  p.on("pageerror", (e) => errores.push(e.message));
  await p.goto(`${base}/atlas/index.html#simulador`);
  await p.waitForSelector("#cargando", { state: "hidden", timeout: 120000 });
  await p.waitForFunction(() => document.querySelectorAll("#sV2 .v2card").length > 0, null, { timeout: 120000 });
  const r = await p.evaluate(() => ({ cards: document.querySelectorAll("#sV2 .v2card").length,
    inputsMin: document.querySelectorAll("#sFich input[type=number], #sFich input[type=range]").length,
    roles: document.querySelectorAll("#sV2 .rolbar").length, curva: document.querySelectorAll("#sV2 svg").length,
    texto: document.querySelector("#sV2").innerText, estiloUnif: document.querySelector("#sOutcome").innerText }));
  comprobar(r.cards >= 1, `simular fichajes: ${r.cards} tarjetas v2`);
  comprobar(r.inputsMin === 0, "simular fichajes: no hay campos de minutos");
  comprobar(r.roles === r.cards && r.curva >= r.cards, "tarjetas con reparto de roles y curva de adaptación");
  comprobar(/50 %/.test(r.texto) && /90 %/.test(r.texto) && /ADAPT%/i.test(r.texto) && /fit/i.test(r.texto), "intervalos 50/90, ADAPT% y Fit");
  comprobar(/Estilo de mapa/.test(r.estiloUnif), "el club muestra el estilo unificado y el de mapa como secundario");
  if (out) await p.screenshot({ path: `${out}/atlas_simulador.png` });
  await p.fill("#sBus", "Corbalan"); await p.waitForTimeout(600);
  const sug = await p.$$eval("#sBusS button", (bs) => bs.map((x) => x.innerText));
  comprobar(sug.some((s) => /sólo simulador v2/.test(s)), "la búsqueda incluye jugadores sólo del simulador (FEB)");
  await p.click("#t-equipo"); await p.waitForTimeout(3000);
  const eq = await p.evaluate(() => ({ inputs: document.querySelectorAll("#eJug input[type=number], #eJug input[type=range]").length, txt: document.querySelector("#eJug").innerText }));
  comprobar(eq.inputs === 0 && /Simulador:/.test(eq.txt), "equipo completo: minutos del simulador, sin campos de minutos");
  const m = await b.newPage({ viewport: { width: 390, height: 900 } });
  m.on("pageerror", (e) => errores.push("móvil: " + e.message));
  await m.goto(`${base}/atlas/index.html#simulador`); await m.waitForSelector("#cargando", { state: "hidden", timeout: 120000 });
  await m.waitForFunction(() => document.querySelectorAll("#sV2 .v2card").length > 0, null, { timeout: 120000 });
  const ancho = await m.evaluate(() => document.documentElement.scrollWidth);
  comprobar(ancho <= 391, `móvil sin desplazamiento horizontal (ancho ${ancho})`);
  if (out) { const c = await m.$("#sV2 .v2card"); if (c) await c.screenshot({ path: `${out}/atlas_simulador_movil.png` }); }
  comprobar(!errores.length, `sin errores de página${errores.length ? ": " + errores.join(" | ") : ""}`);
  await b.close();
  console.log(fallos.length ? `${fallos.length} comprobaciones fallidas` : "todas las comprobaciones pasan");
  process.exit(fallos.length ? 1 : 0);
})();
