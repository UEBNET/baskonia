// F4 v4.1: genera la lectura de fichaje (jugador 2025-26 hacia Baskonia 2026-27) y comprueba desbordes de hoja,
// ausencia de Fit/ADAPT y presencia de Landing y confianza.   node prueba_informes_v41.js <base> <dir_salida> [jugador]
const { chromium } = require("playwright");
const fs = require("fs");
const [base, out, jug] = process.argv.slice(2);
fs.mkdirSync(out, { recursive: true });
(async () => {
  const br = await chromium.launch();
  const pg = await br.newPage({ viewport: { width: 1440, height: 1000 } });
  const err = [];
  pg.on("pageerror", (e) => err.push(String(e)));
  await pg.goto(base + "atlas/index.html", { waitUntil: "load", timeout: 120000 });
  await pg.waitForTimeout(12000);
  const r1 = await pg.evaluate(async (palabras) => {
    await cargarSim();
    for (let i = 0; i < 100 && !(window.KernoV41 && KernoV41.listo() && window.CernoV40 && CernoV40.listo()); i++) await new Promise((o) => setTimeout(o, 200));
    const j = JG.filter((x) => x.temporada === "2025-26" && palabras.every((w) => (x.nombre + " " + x.nombre_club).toLowerCase().includes(w))).sort((a, b) => b.min - a.min)[0];
    if (!j) return { error: "sin jugador" };
    const c = BY.get(j.clave), al = META.clubes_con_nombre.baskonia, k = al.claves.find((x) => x.startsWith("euroleague:"));
    st.inf = { temp: j.temporada, liga: j.liga, club: c.clave_club, jug: jKey(j), sim: true, dTemp: "2026-27", dLiga: "euroleague", dClub: k, rol: "ROTACION" };
    st.inf.rolDe = `${st.inf.jug}|${k}:2026-27`;
    const tb = document.querySelector("#t-informe");
    if (tb) tb.click();
    construirInforme(); ifControles(); await pintarInforme();
    await new Promise((o) => setTimeout(o, 3000));
    const hojas = [...document.querySelectorAll(".ifsheet")];
    const txt = hojas.map((h) => h.innerText).join("\n");
    const des = hojas.map((h) => h.scrollHeight - h.clientHeight);
    return { jugador: j.nombre, hojas: des.length, desbordes: des.filter((x) => x > 2).length, fit: /Índice Fit/.test(txt), adapt: /ADAPT/.test(txt),
      landing: (txt.match(/Landing[^\n]{0,140}/g) || []).slice(0, 5), confianza: (txt.match(/confianza (alta|moderada|baja)/g) || []).length };
  }, (jug || "jabari+parker").split("+"));
  console.log("LECTURA", JSON.stringify(r1, null, 1));
  const hs = await pg.$$(".ifsheet");
  for (let i = 0; i < Math.min(hs.length, 16); i++) await hs[i].screenshot({ path: `${out}/lectura_${String(i + 1).padStart(2, "0")}.png` });
  console.log("errores", err.slice(0, 5));
  await br.close();
})();
