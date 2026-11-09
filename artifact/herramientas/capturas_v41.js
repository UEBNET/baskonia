// F4 v4.1: capturas obligatorias del simulador con el ecosistema (1440 y 390 px, claro y oscuro) y control de scroll horizontal.
// node capturas_v41.js <base> <dir_salida>
const { chromium } = require("playwright");
const fs = require("fs");
const [base, out] = process.argv.slice(2);
fs.mkdirSync(out, { recursive: true });
(async () => {
  const br = await chromium.launch();
  for (const ancho of [1440, 390]) for (const tema of ["light", "dark"]) {
    const pg = await br.newPage({ viewport: { width: ancho, height: 900 }, colorScheme: tema, deviceScaleFactor: 2 });
    const err = [];
    pg.on("pageerror", (e) => err.push(String(e)));
    await pg.goto(base + "atlas/index.html#simulador", { waitUntil: "load", timeout: 120000 });
    await pg.click("#t-simulador");
    await pg.waitForTimeout(15000);
    const r = await pg.evaluate(async () => {
      escenarioEjemplo(); pintarSim();
      for (let i = 0; i < 100 && !document.querySelector("#sEcoV41 .v41eco"); i++) await new Promise((o) => setTimeout(o, 200));
      return { eco: !!document.querySelector("#sEcoV41 .v41eco"), scrollX: document.documentElement.scrollWidth - window.innerWidth };
    });
    const el = await pg.$("#sEcoV41");
    if (el) await el.screenshot({ path: `${out}/ecosistema_${ancho}_${tema}.png` });
    const card = await pg.$("#sV2 .v2card");
    if (card) await card.screenshot({ path: `${out}/fichaje_${ancho}_${tema}.png` });
    console.log(ancho, tema, JSON.stringify(r), "errores", err.length);
    await pg.close();
  }
  await br.close();
})();
