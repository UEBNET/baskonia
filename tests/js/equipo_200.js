// Prueba en navegador de «Simular equipo completo» (200' siempre; rojo y cambio de rol a mano si no cuadra) y del recorte
// a 0 del rango de puntos/100 con su nota al pie. Carpeta servida con la forma del Artifact (ver artifact/empaquetar.py):
//   node tests/js/equipo_200.js http://localhost:8765
const { chromium } = require("playwright");
const base = process.argv[2] || "http://localhost:8765";
const fallos = [];
const comprobar = (c, txt) => { if (!c) fallos.push(txt); console.log(`${c ? "ok   " : "FALLO"} ${txt}`); };
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROMIUM || "/opt/pw-browsers/chromium" });
  const p = await b.newPage({ viewport: { width: 1400, height: 1000 } }), errores = [];
  p.on("pageerror", (e) => errores.push(e.message));
  await p.goto(`${base}/atlas/index.html#equipo`); await p.waitForSelector("#cargando", { state: "hidden", timeout: 120000 }); await p.waitForTimeout(6000);
  const leer = () => p.evaluate(() => { const s = eqEstado(), e = document.getElementById("eTot");
    return { M: s.M, estado: s.cuadre && s.cuadre.estado, rojo: e.classList.contains("mal"), txt: e.innerText }; });
  const fijar = (f) => p.evaluate(f).then(() => p.waitForTimeout(5000));
  // plantilla real de 15 jugadores de Baskonia 2025-26
  await fijar(() => { const c = CL.find((x) => x.liga === "euroleague" && x.temporada === "2025-26" && /Baskonia/.test(x.nombre_club));
    st.eq.jug = (ROSTER.get(c.clave) || []).filter((j) => j.min > 50).map((j) => ({ k: jKey(j) })); pintarEq(); });
  await fijar(() => { st.eq.jug.forEach((f, i) => { f.rol = i < 5 ? "TITULAR" : i < 9 ? "ROTACION" : "PROFUNDIDAD"; }); pintarEq(); });
  let r = await leer();
  comprobar(r.estado === "cuadra" && Math.abs(r.M - 200) < 0.05 && !r.rojo, `roles que caben en sus franjas: reparte ${r.M.toFixed(1)}' y cuadra`);
  await fijar(() => { st.eq.jug.forEach((f) => { f.rol = "TITULAR"; }); pintarEq(); });
  r = await leer();
  comprobar(r.estado === "sobran" && r.rojo && /Cambia a mano el rol/.test(r.txt) && /Sobran/.test(r.txt), "quince titulares: cuadro en rojo, «Sobran» y cambio de rol a mano");
  await fijar(() => { st.eq.jug = st.eq.jug.slice(0, 6); st.eq.jug.forEach((f) => { f.rol = "RESIDUAL"; }); pintarEq(); });
  r = await leer();
  comprobar(r.estado === "faltan" && r.rojo && /Faltan/.test(r.txt), "seis residuales: cuadro en rojo y «Faltan»");
  // puntos/100: extremo inferior recortado a 0 con su nota
  const n = await p.evaluate(async () => { await cargarSim(); const rec = [...SIMD.jug.values()].find((x) => /Gimeno/.test(x.nombre) && x.temporada === "2025-26");
    const club = [...SIMD.porClub.values()].find((c) => c.liga === "nba" && c.temporada === "2026-27");
    const s = SIM2.simular({ rec, club, rol: "PROFUNDIDAD" }), d = s.produccion_p100.pts_p100; return { lo: d.lo90, marca: d.recorte_cero, nota: notaCero(s) }; });
  comprobar(n.lo === 0 && n.marca && /no pueden? ser negativos?/.test(n.nota) && /puntos\/100/.test(n.nota) && /nivel/.test(n.nota), "puntos/100: rango desde 0 con nota al pie y sus factores");
  comprobar(!errores.length, "sin errores de página" + (errores.length ? ": " + errores.slice(0, 3).join(" | ") : ""));
  await b.close();
  console.log(fallos.length ? `${fallos.length} comprobaciones fallidas` : "todas las comprobaciones pasan");
  process.exit(fallos.length ? 1 : 0);
})();
