// F4 v4.1: prueba de la capa del ecosistema en el Atlas (escenario de ejemplo: alta + baja) — node prueba_v41.js <base> <png>
const { chromium } = require("playwright");
const [base, png, tema] = process.argv.slice(2);
(async () => {
  const br = await chromium.launch();
  const pg = await br.newPage({ viewport: { width: 1440, height: 1000 }, colorScheme: tema === "oscuro" ? "dark" : "light" });
  const err = []; pg.on("pageerror", (e) => err.push(String(e))); pg.on("console", (m) => { if (m.type() === "error") err.push(m.text()); });
  await pg.goto(base + "atlas/index.html#simulador", { waitUntil: "load", timeout: 120000 });
  await pg.click("#t-simulador"); await pg.waitForTimeout(15000);
  // escenario de ejemplo del Atlas (dos fichajes que encajan + la baja del jugador con más minutos)
  const r = await pg.evaluate(async () => {
    const t0 = performance.now();
    escenarioEjemplo(); pintarSim();
    await new Promise((ok) => setTimeout(ok, 200));
    for (let i = 0; i < 100 && !(document.querySelector("#sEcoV41 .v41eco")); i++) await new Promise((ok) => setTimeout(ok, 200));
    const eco = document.querySelector("#sEcoV41");
    return { ms: Math.round(performance.now() - t0), eco: eco ? eco.innerText.slice(0, 2500) : null,
      fit: document.body.innerText.includes("Índice Fit"), adapt: /ADAPT/.test(document.body.innerText),
      landing: [...document.querySelectorAll("#sV2 .v2card")].map((c) => (c.innerText.match(/Landing[^\n]*\n?[^\n]*/) || [""])[0]).slice(0, 3),
      conf: document.querySelectorAll("#sV2 .k-conf").length };
  });
  console.log(JSON.stringify(r, null, 1)); console.log("errores", err.slice(0, 8));
  const el = await pg.$("#p-simulador"); if (el && png) await el.screenshot({ path: png });
  await br.close();
})();
