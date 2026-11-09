// Prueba en navegador del informe de fichaje (PDF): percentiles y textos frente a la liga de referencia (la del club de
// destino o, sin destino, la del jugador), con los grupos por liga de atlas/informe/<t>.json → ligas.
//   node tests/js/informe_liga.js http://localhost:8765
const { chromium } = require("playwright");
const base = process.argv[2] || "http://localhost:8765";
const fallos = [];
const comprobar = (c, txt) => { if (!c) fallos.push(txt); console.log(`${c ? "ok   " : "FALLO"} ${txt}`); };
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROMIUM || "/opt/pw-browsers/chromium" });
  const p = await b.newPage({ viewport: { width: 1400, height: 1000 } }), errores = [];
  p.on("pageerror", (e) => errores.push(e.message));
  await p.goto(`${base}/atlas/index.html#informe`); await p.waitForSelector("#cargando", { state: "hidden", timeout: 120000 }); await p.waitForTimeout(4000);
  const caso = (dest) => p.evaluate(async (dest) => {
    const g = JG.filter((j) => /Gimeno/.test(j.nombre)).sort((a, b) => b.temporada.localeCompare(a.temporada))[0];
    st.inf.jug = jKey(g); st.inf.temp = g.temporada; st.inf.liga = g.liga; st.inf.club = BY.get(g.clave).clave_club; st.inf.sim = !!dest;
    if (dest) { const c = CL.find((x) => x.liga === dest[0] && x.temporada === "2025-26" && new RegExp(dest[1]).test(x.nombre_club)); st.inf.dLiga = dest[0]; st.inf.dTemp = "2025-26"; st.inf.dClub = c.clave_club; }
    await pintarInforme(); await new Promise((r) => setTimeout(r, 1500));
    const t = document.getElementById("ifPages").innerText.replace(/\s+/g, " ");
    const fuera = (t.match(/[^.;]{0,40}Euroliga[^.;]{0,30}/g) || []).filter((x) => !/Euroliga = 0\)/.test(x));
    return { pool: IF_POOL, puesto: /frente a los [a-z]+ de la (Liga Endesa|Tercera FEB)/.test(t), supera: (t.match(/Supera al 80 % de los jugadores de su puesto en la [A-Za-z ]+/) || [""])[0], fuera };
  }, dest);
  const a = await caso(["acb", "Bilbao"]);
  comprobar(a.pool === "acb" && a.puesto && /Liga Endesa/.test(a.supera), "con destino Bilbao: percentiles y textos frente a la Liga Endesa");
  comprobar(!a.fuera.length, "sin «Euroliga» como referencia (sólo en la tabla que compara ligas), también en la química" + (a.fuera.length ? ": " + a.fuera.slice(0, 2).join(" | ") : ""));
  const s = await caso(null);
  comprobar(s.pool === "feb3" && /Tercera FEB/.test(s.supera), "sin destino: frente a su propia liga (Tercera FEB)");
  comprobar(!errores.length, "sin errores de página" + (errores.length ? ": " + errores.slice(0, 3).join(" | ") : ""));
  await b.close();
  console.log(fallos.length ? `${fallos.length} comprobaciones fallidas` : "todas las comprobaciones pasan");
  process.exit(fallos.length ? 1 : 0);
})();
