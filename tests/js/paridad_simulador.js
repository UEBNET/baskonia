// Paridad del motor del navegador (artifact/atlas/simulador_v2.js) con la referencia Python (bbfit.simulador.simular).
//   python -c "from bbfit import sim_exportar as E; E.paridad()"     # casos de referencia → data/artifact/simulador/paridad.json
//   node tests/js/paridad_simulador.js [carpeta]                     # compara medias (tolerancias de error Monte Carlo)
const fs = require("fs"), path = require("path");
const dir = process.argv[2] || path.join(__dirname, "..", "..", "data", "artifact", "simulador");
const SIM2 = require(path.join(__dirname, "..", "..", "artifact", "atlas", "simulador_v2.js"));
const leer = (f) => JSON.parse(fs.readFileSync(path.join(dir, f), "utf8"));
const D = SIM2.cargar(leer("meta.json"), leer("jugadores.json"), leer("clubes.json"));
const casos = leer("paridad.json");
const TOL = { minutos: 1.2, rol: 0.07, pts_p100: 1.0, ts_pct: 1.2, usg_pct: 1.0, adapt: 0.6, d_net: 0.5 };
let fallos = 0;
casos.forEach((c) => {
  const rec = D.jug.get(c.rec), club = D.porClub.get(c.club);
  const t0 = Date.now(), r = SIM2.simular({ rec, club, nSim: 4000 }), ms = Date.now() - t0;
  const dif = { minutos: r.minutos.media - c.minutos, pts_p100: r.produccion_p100.pts_p100.media - c.pts_p100,
    ts_pct: r.produccion_p100.ts_pct.media - c.ts_pct, usg_pct: r.produccion_p100.usg_pct.media - c.usg_pct,
    adapt: r.adaptacion.adapt_pct_temporada.media - c.adapt, d_net: r.equipo.d_net - c.d_net,
    rol: Math.max(...SIM2.ROLES.map((k) => Math.abs(r.roles[k] - c.roles[k]))) };
  const mal = Object.entries(dif).filter(([k, v]) => !(Math.abs(v) <= TOL[k]));
  if (mal.length) fallos++;
  console.log(`${mal.length ? "FALLO" : "ok   "} ${c.nombre} → ${c.club_nombre} (${ms} ms): ` + Object.entries(dif).map(([k, v]) => `${k} ${v >= 0 ? "+" : ""}${v.toFixed(2)}`).join(" · ")
    + (mal.length ? `  [fuera de tolerancia: ${mal.map((x) => x[0]).join(", ")}]` : ""));
});
console.log(fallos ? `${fallos} de ${casos.length} casos fuera de tolerancia` : `paridad: ${casos.length} de ${casos.length} casos dentro de tolerancia`);
process.exit(fallos ? 1 : 0);
