// Prueba en navegador de la vara de la Mesa (normalización v3.2: «esta liga = 0»).
// Requiere una carpeta servida con la forma del Artifact (index.html = artifact/mesa-multiliga.html, datos/ con
// normalizados/vara.json; ver artifact/empaquetar.py) y Playwright con Chromium:
//   node tests/js/mesa_vara.js http://localhost:8765
// La conversión numérica se contrasta aparte con la referencia Python bbnorm3.destino.desde_el (misma fórmula).
const { chromium } = require("playwright");
const base = process.argv[2] || "http://localhost:8765";
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROMIUM || "/opt/pw-browsers/chromium" });
  const errores = [], fallos = [];
  const comprobar = (c, txt) => { if (!c) fallos.push(txt); console.log(`${c ? "ok   " : "FALLO"} ${txt}`); };
  const p = await b.newPage({ viewport: { width: 1400, height: 1000 } });
  p.on("pageerror", (e) => errores.push(e.message));
  await p.goto(`${base}/index.html`); await p.waitForTimeout(3000);
  await p.click("#srcSeg button[data-src=normalizados]");
  await p.waitForFunction(() => document.querySelectorAll("#tablebox tbody tr").length > 0, null, { timeout: 120000 });
  const fila = () => p.evaluate(() => {
    const t = document.querySelector("#tablebox table"), h = [...t.querySelectorAll("thead th")].map((x) => x.innerText.trim().toUpperCase());
    const i = h.findIndex((x) => x.startsWith("PTS/100")), tr = t.querySelector("tbody tr");
    return { nombre: tr.children[0].innerText.trim(), pts: tr.children[i].innerText.trim(), boton: document.querySelector("#srcSeg button[data-src=normalizados]").innerText };
  });
  const v = await p.evaluate(() => ({ visible: !document.getElementById("varaGrp").hidden, n: document.getElementById("varaSel").options.length, val: document.getElementById("varaSel").value }));
  comprobar(v.visible && v.n >= 15 && v.val === "euroleague", `selector de vara visible con ${v.n} ligas y EuroLeague por defecto`);
  const el = await fila();
  await p.selectOption("#varaSel", "acb"); await p.waitForTimeout(4000);
  const acb = await fila();
  comprobar(/ACB/.test(acb.boton), `el botón indica la vara («${acb.boton}»)`);
  comprobar(el.pts !== acb.pts, `los valores cambian con la vara (${el.nombre}: ${el.pts} → ${acb.pts} pts/100)`);
  await p.selectOption("#varaSel", "euroleague"); await p.waitForTimeout(4000);
  comprobar((await fila()).pts === el.pts, "volver a EuroLeague devuelve los valores publicados");
  await p.evaluate(() => ebIr("metodologia", "normalizacion")); await p.waitForTimeout(5000);
  await p.selectOption("#nlVara", "feb1"); await p.waitForTimeout(2000);
  const nl = await p.evaluate(() => ({ t: document.getElementById("nlRankT").innerText,
    ref: document.querySelector("#nlRank .nl-rrow.ref .nl-lname").innerText.trim(),
    el: [...document.querySelectorAll("#nlRank .nl-rrow:not(.ref) .nl-lname")].some((x) => /EuroLeague/.test(x.innerText)) }));
  comprobar(/Primera FEB/.test(nl.t) && /Primera FEB/.test(nl.ref), `Normalización de ligas: la vara es la fila de referencia («${nl.ref}»)`);
  comprobar(nl.el, "la EuroLeague entra en el ranking cuando no es la vara");
  comprobar(!errores.length, "sin errores de página" + (errores.length ? ": " + errores.slice(0, 3).join(" | ") : ""));
  await b.close();
  console.log(fallos.length ? `${fallos.length} comprobaciones fallidas` : "todas las comprobaciones pasan");
  process.exit(fallos.length ? 1 : 0);
})();
